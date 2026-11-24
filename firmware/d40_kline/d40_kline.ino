/* Teensy 4.1 dual-channel SLCAN (Lawicel) adapter for the TCU bench,
 * plus a K-line bridge for the D40 Frontier ECM bench (2026-11-23).
 *
 * Derived from alldogsoffroad/8hp-teensy-flasher firmware/teensy_slcan.ino (GPL-3.0).
 * The two SLCAN channels and the telemetry lines are unchanged; the K-line
 * bridge is added on a third USB serial port.
 *
 * USB type: "Triple Serial" (Arduino IDE: Tools > USB Type > Triple Serial;
 * arduino-cli: --fqbn "teensy:avr:teensy41:usb=serial3").
 *   first USB serial port  (Serial)     <-> CAN1  (pins 22 TX / 23 RX)  -> TCU pins 5/6 (CAN-C)
 *   second USB serial port (SerialUSB1) <-> CAN2  (pins  1 TX /  0 RX)  -> TCU pins 3/4 (shifter bus)
 *   third USB serial port  (SerialUSB2) <-> K-line on Serial2 (pin 8 TX2 -> converter RX,
 *                                            pin 7 RX2 <- converter TX); see the K-line
 *                                            command list below.
 * Each CAN pin pair needs a 3.3 V CAN transceiver (for example SN65HVD230).
 *
 * On Linux each port becomes a SocketCAN interface:
 *   sudo slcand -o -s6 -t hw -S 2000000 /dev/ttyACM0 can0 && sudo ip link set can0 up
 *   sudo slcand -o -s6 -t hw -S 2000000 /dev/ttyACM1 can1 && sudo ip link set can1 up
 *
 * Supported SLCAN commands: S0..S8 (bit rate), S9 (666.667 kbit/s, project extension), O (open), L (open listen-only), C (close), t/T (send standard / extended frame), r/R (remote frame),
 * V (version), N (serial number), F (status flags), Z0/Z1 (timestamps), M/m (acceptance filter:
 * accepted, all frames are passed), E (project extension: error state,
 * reply "E<TEC 2 hex><REC 2 hex><ESR1 8 hex>", then ESR1 is read-cleared),
 * P0/P1/P2 (project extension, kept until reset: P1 = every later O opens LISTEN-ONLY, P2 =
 * listen-only plus automatic bit rate: after 200 ms with bus errors and no valid frame the
 * channel steps through 500k, 666.667k, 1M, 250k, 125k, 800k and reports each change as a marker frame
 * with extended ID 0x1FFFFF00 and data = new rate in kbit/s, 2 bytes big-endian).
 * Listen-only nodes never acknowledge and never send error flags: use them for sniffing.
 * K (project extension, channel must be closed): internal loop-back self-test, nothing goes on
 * the bus; sends one 11-bit and one 29-bit frame to itself, reply "K<std ok><ext ok>" (1/0). Received frames: "tIIILDD..[TTTT]\r" / "TIIIIIIIILDD..\r".
 *
 * Library: FlexCAN_T4 (included with Teensyduino).
 */
#include <FlexCAN_T4.h>

FlexCAN_T4<CAN1, RX_SIZE_256, TX_SIZE_32> can_a;
FlexCAN_T4<CAN2, RX_SIZE_256, TX_SIZE_32> can_b;

struct Channel {
  Stream *port;
  bool open;
  uint8_t passive;            /* 0 normal, 1 listen-only, 2 listen-only + automatic bit rate */
  bool listen;                /* currently opened listen-only */
  uint8_t auto_idx;
  uint32_t last_check_ms, good_since_check;
  uint8_t last_rec;
  bool timestamps;
  uint32_t bitrate;
  char line[40];
  uint8_t len;
  uint32_t rx_count, tx_count, errors;
};

static Channel ch[2];

/* H: saturation hail (project extension, round 41): H<sec> sends 7E1 # 54 FF 3D 22
 * (the boot-session entry magic) every ~110 us for <sec> seconds.
 * The boot rom seeds within sub-ms of power-up; a USB-paced loop is too slow (round 41
 * addendum 3). ~110 us keeps ~35% of bus slots free so higher-ID replies (7E9) still win
 * arbitration. 'h' or C stops it early. Channel must be open and not listen-only. */
static uint32_t hail_until_ms[2];
/* Y/y: auto-reply rules - the 500k boot handshake needs sub-ms
 * answers a USB-paced host cannot deliver. Rules act on the receiving channel.
 * Y<8hex>  : arm hail-answer: rx 7E1 # 54 FF 3D 22 -> tx 7E9 # <seed4B>
 * Y0       : disarm hail-answer
 * y<16hex><16hex> : arm byte-match: rx 7E1 # <match8B> -> tx 7E9 # <reply8B>
 * y0       : disarm byte-match */
static uint8_t auto_seed[2][4];  static bool auto_hail[2];
static uint8_t auto_match[2][8]; static uint8_t auto_resp[2][8]; static bool auto_chal[2];
static uint32_t hail_last_us[2];
static bool hail_pulse[2];     /* G mode: 300 ms storm / 300 ms silence so starved
                                * higher-ID replies (7E9 seed, 7Fx telemetry) get air;
                                * continuous saturation provably jams them (round 41) */

/* A: power-feed monitor (round 41). 'A1' samples the box 12V feed through a divider
 * on pin 14 (A0) every loop pass (~30-50 kS/s) and emits "P<feed millivolts>" on the
 * FIRST port whenever the value moves > threshold or every 50 ms heartbeat — the same
 * timeline as CAN frames, so feed dips/pulses correlate with the boot-session opening.
 * Divider: 33k (feed->pin) + 10k (pin->GND), ratio 4.3. 'A0' stops it. */
static bool power_mon = false;
static bool storm_fast = false;          /* B1/B0: LED fast-blink while the storm is active */
static const float    PWR_RATIO = 4.9f;   /* divider re-cut 2026-10-31 (9420a8d) */
static const uint16_t PWR_DELTA = 250;    /* emit when feed moves > 250 mV */
static uint32_t       pwr_last_emit_ms;
static uint16_t       pwr_last_mv;
/* Bench ammeter (2026-11-02): ACS712 5 A module in the TCU supply lead (IP+ from
 * the PSU, IP- to the harness); OUT through a 10k/15k divider to pin 15 (A1).
 * 185 mV/A centred at 2.5 V -> after the 0.6 divider, 1.5 V at zero current.
 * 32-sample averaging per emission; "A<milliamps>" on the FIRST port, same
 * threshold/heartbeat scheme as the P feed line. */
static const float    AM_DIV  = 0.6f;
static const float    AM_SENS = 0.185f;   /* volts per amp */
/* Bench leads wired IP- -> supply (reads negative): sign flipped in software.
 * AM_ZERO is ADDITIVE with the flipped formula: it absorbs the module's own
 * zero-current offset (this board sits ~+26 mV high, i.e. ~+142 mA raw).
 * Calibrated 2026-11-02 against the PSU: bench-on 167 mA reads ~173. */
static const int16_t  AM_ZERO  = 142;
static const int16_t  AM_DELTA = 20;      /* mA step for immediate emission */
static uint32_t       am_last_emit_ms;
static int16_t        am_last_ma;

/* S9 = 666.667 kbit/s, the Bosch user boot MAT plant-entry rate (spec 17): 24 MHz / (2 x 18 tq).
 * Given as 666666: FlexCAN_T4 searches divisors with integer division and rejects 666667. */
static const uint32_t kRates[10] = { 10000, 20000, 50000, 100000, 125000, 250000, 500000,
                                     800000, 1000000, 666666 };

static void set_rate(int i) {
  const FLEXCAN_RXTX mode = ch[i].listen ? LISTEN_ONLY : TX;
  if (i == 0) {
    can_a.setBaudRate(ch[0].bitrate, mode);
  } else {
    can_b.setBaudRate(ch[1].bitrate, mode);
  }
}

static const uint32_t kAutoRates[6] = { 500000, 666666, 1000000, 250000, 125000, 800000 };
#define AUTO_RATES (sizeof kAutoRates / sizeof kAutoRates[0])

static uint8_t rx_errors(int i) {
  return (uint8_t)(((i == 0 ? FLEXCAN1_ECR : FLEXCAN2_ECR) >> 8) & 0xFF);
}

/* Bus errors since the last call. In listen-only mode FlexCAN does not change the error counters,
 * but it still sets the error flags in ESR1 (bit1/bit0/ack/CRC/form/stuff, bits 15..10), which are
 * cleared by reading ESR1. */
static bool bus_errors_seen(int i) {
  const uint32_t esr = i == 0 ? FLEXCAN1_ESR1 : FLEXCAN2_ESR1;
  return (esr & 0x0000FC00u) != 0u;
}

static bool write_frame(int i, const CAN_message_t &m) {
  return i == 0 ? can_a.write(m) > 0 : can_b.write(m) > 0;
}

static int hexval(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return -1;
}

static bool parse_hex(const char *s, uint8_t n, uint32_t *out) {
  uint32_t v = 0;
  for (uint8_t k = 0; k < n; k++) {
    int h = hexval(s[k]);
    if (h < 0) return false;
    v = (v << 4) | (uint32_t)h;
  }
  *out = v;
  return true;
}

static void reply(int i, const char *s) { ch[i].port->print(s); }

/* FlexCAN error counters (ECR: TX count bits 7..0, RX count bits 15..8) and status (ESR1) */
static void cmd_error_state(int i) {
  char buf[24];
  const uint32_t ecr = i == 0 ? FLEXCAN1_ECR : FLEXCAN2_ECR;
  const uint32_t esr = i == 0 ? FLEXCAN1_ESR1 : FLEXCAN2_ESR1;
  snprintf(buf, sizeof buf, "E%02lX%02lX%08lX\r", (unsigned long)(ecr & 0xFF),
           (unsigned long)((ecr >> 8) & 0xFF), (unsigned long)esr);
  reply(i, buf);
}
static void ok(int i) { ch[i].port->write('\r'); }
static void err(int i) { ch[i].port->write('\a'); }

/* t/T/r/R: send a frame */
static void cmd_send(int i, const char *s, bool ext, bool rtr) {
  const uint8_t idlen = ext ? 8 : 3;
  uint32_t id, dlc, b;
  CAN_message_t m;

  if (!ch[i].open || ch[i].listen || !parse_hex(s + 1, idlen, &id) || !parse_hex(s + 1 + idlen, 1, &dlc) ||
      dlc > 8) {
    err(i);
    return;
  }
  m.id = id;
  m.flags.extended = ext;
  m.flags.remote = rtr;
  m.len = (uint8_t)dlc;
  if (!rtr) {
    for (uint8_t k = 0; k < dlc; k++) {
      if (!parse_hex(s + 2 + idlen + 2 * k, 2, &b)) {
        err(i);
        return;
      }
      m.buf[k] = (uint8_t)b;
    }
  }
  if (write_frame(i, m)) {
    ch[i].tx_count++;
    ch[i].port->write(ext ? 'Z' : 'z');
    ok(i);
  } else {
    ch[i].errors++;
    err(i);
  }
}

/* K: loop-back self-test of standard and extended reception (no bus traffic) */
static void cmd_selftest(int i) {
  CAN_message_t t, r;
  bool got_std = false, got_ext = false;
  char buf[8];

  if (ch[i].open) { err(i); return; }
  if (i == 0) can_a.enableLoopBack(true); else can_b.enableLoopBack(true);
  for (int k = 0; k < 2; k++) {
    t = CAN_message_t();
    t.id = k == 0 ? 0x123 : 0x18DAF110;
    t.flags.extended = k == 1;
    t.len = 2;
    t.buf[0] = 0x5A;
    t.buf[1] = (uint8_t)k;
    if (i == 0) can_a.write(t); else can_b.write(t);
  }
  for (uint32_t start = millis(); millis() - start < 50u;) {
    if ((i == 0 ? can_a.read(r) : can_b.read(r)) && r.buf[0] == 0x5A) {
      if (r.flags.extended && r.id == 0x18DAF110) got_ext = true;
      if (!r.flags.extended && r.id == 0x123) got_std = true;
    }
  }
  if (i == 0) can_a.enableLoopBack(false); else can_b.enableLoopBack(false);
  snprintf(buf, sizeof buf, "K%d%d\r", got_std ? 1 : 0, got_ext ? 1 : 0);
  reply(i, buf);
}

static void handle_line(int i) {
  const char *s = ch[i].line;
  char buf[16];

  switch (s[0]) {
    case 'S':
      if (ch[i].open || s[1] < '0' || s[1] > '9') { err(i); break; }
      ch[i].bitrate = kRates[s[1] - '0'];
      set_rate(i);
      ok(i);
      break;
    case 'O':
    case 'L':
      ch[i].listen = s[0] == 'L' || ch[i].passive != 0;
      ch[i].auto_idx = 0;
      for (uint8_t k = 0; k < AUTO_RATES; k++) {
        if (kAutoRates[k] == ch[i].bitrate) ch[i].auto_idx = k;
      }
      set_rate(i);
      ch[i].open = true;
      ch[i].last_check_ms = millis();
      ch[i].good_since_check = 0;
      ch[i].last_rec = rx_errors(i);
      ok(i);
      break;
    case 'P':
      if (s[1] < '0' || s[1] > '2') { err(i); break; }
      ch[i].passive = (uint8_t)(s[1] - '0');
      ok(i);
      break;
    case 'C':
      ch[i].open = false;
      ok(i);
      break;
    case 'A':
      power_mon = s[1] == '1';
      pwr_last_emit_ms = 0;                 /* force a heartbeat line immediately */
      ok(i);
      break;
    case 'B':                                /* LED storm indicator: B1 fast, B0 slow (global) */
      storm_fast = s[1] == '1';
      ok(i);
      break;
    case 't': cmd_send(i, s, false, false); break;
    case 'H': {
      uint32_t secs = 0;
      bool bad = false;
      for (const char *p = s + 1; *p; p++) {
        if (*p < '0' || *p > '9') { bad = true; break; }
        secs = secs * 10u + (uint32_t)(*p - '0');
      }
      if (bad || secs == 0u || secs > 60u || !ch[i].open || ch[i].listen) { err(i); break; }
      hail_until_ms[i] = millis() + secs * 1000u;
      ok(i);
      break;
    }
    case 'h':
      hail_until_ms[i] = 0;
      ok(i);
      break;
    case 'G': {
      uint32_t secs = 0;
      bool bad = false;
      for (const char *p = s + 1; *p; p++) {
        if (*p < '0' || *p > '9') { bad = true; break; }
        secs = secs * 10u + (uint32_t)(*p - '0');
      }
      if (bad || secs == 0u || secs > 60u || !ch[i].open || ch[i].listen) { err(i); break; }
      hail_until_ms[i] = millis() + secs * 1000u;
      hail_pulse[i] = true;
      ok(i);
      break;
    }
    case 'g':
      hail_until_ms[i] = 0;
      hail_pulse[i] = false;
      ok(i);
      break;
    case 'T': cmd_send(i, s, true, false); break;
    case 'Y': {
      uint32_t v;
      if (s[1] == '0' && !s[2]) { auto_hail[i] = false; ok(i); break; }
      if (strlen(s) != 9 || !parse_hex(s + 1, 8, &v)) { err(i); break; }
      auto_seed[i][0] = v >> 24; auto_seed[i][1] = v >> 16; auto_seed[i][2] = v >> 8; auto_seed[i][3] = v;
      auto_hail[i] = true; ok(i); break;
    }
    case 'y': {
      uint32_t a, b;
      if (s[1] == '0' && !s[2]) { auto_chal[i] = false; ok(i); break; }
      if (strlen(s) != 33 || !parse_hex(s + 1, 8, &a) || !parse_hex(s + 9, 8, &b)) { err(i); break; }
      auto_match[i][0] = a >> 24; auto_match[i][1] = a >> 16; auto_match[i][2] = a >> 8; auto_match[i][3] = a;
      auto_match[i][4] = b >> 24; auto_match[i][5] = b >> 16; auto_match[i][6] = b >> 8; auto_match[i][7] = b;
      if (!parse_hex(s + 17, 8, &a) || !parse_hex(s + 25, 8, &b)) { err(i); break; }
      auto_resp[i][0] = a >> 24; auto_resp[i][1] = a >> 16; auto_resp[i][2] = a >> 8; auto_resp[i][3] = a;
      auto_resp[i][4] = b >> 24; auto_resp[i][5] = b >> 16; auto_resp[i][6] = b >> 8; auto_resp[i][7] = b;
      auto_chal[i] = true; ok(i); break;
    }
    case 'r': cmd_send(i, s, false, true); break;
    case 'R': cmd_send(i, s, true, true); break;
    case 'V': reply(i, "V0101\r"); break;
    case 'v': reply(i, "vTCU1\r"); break;
    case 'N': snprintf(buf, sizeof buf, "N%04X\r", i == 0 ? 0xA001 : 0xA002); reply(i, buf); break;
    case 'F': reply(i, "F00\r"); break;
    case 'E': cmd_error_state(i); break;
    case 'K': cmd_selftest(i); break;
    case 'Z': ch[i].timestamps = s[1] == '1'; ok(i); break;
    case 'M':
    case 'm':
    case 'X':
    case 'W':
    case 'U': ok(i); break;
    default: err(i); break;
  }
}

static void poll_port(int i) {
  while (ch[i].port->available()) {
    char c = (char)ch[i].port->read();
    if (c == '\r') {
      ch[i].line[ch[i].len] = '\0';
      if (ch[i].len) handle_line(i);
      ch[i].len = 0;
    } else if (c != '\n' && ch[i].len < sizeof ch[i].line - 1) {
      ch[i].line[ch[i].len++] = c;
    }
  }
}

static void forward(int i, const CAN_message_t &m) {
  char out[40];
  int n;

  if (!ch[i].open) return;
  if (!ch[i].listen && !m.flags.extended && m.id == 0x7E1) {
    if (auto_hail[i] && m.len == 4 &&
        m.buf[0] == 0x54 && m.buf[1] == 0xFF && m.buf[2] == 0x3D && m.buf[3] == 0x22) {
      CAN_message_t a;
      a.id = 0x7E9; a.flags.extended = false; a.flags.remote = false; a.len = 4;
      memcpy(a.buf, auto_seed[i], 4);
      write_frame(i, a);
    } else if (auto_chal[i] && m.len == 8 && memcmp(m.buf, auto_match[i], 8) == 0) {
      CAN_message_t a;
      a.id = 0x7E9; a.flags.extended = false; a.flags.remote = false; a.len = 8;
      memcpy(a.buf, auto_resp[i], 8);
      write_frame(i, a);
    }
  }
  ch[i].rx_count++;
  ch[i].good_since_check++;
  if (m.flags.extended) {
    n = snprintf(out, sizeof out, "%c%08lX%u", m.flags.remote ? 'R' : 'T',
                 (unsigned long)m.id, m.len);
  } else {
    n = snprintf(out, sizeof out, "%c%03lX%u", m.flags.remote ? 'r' : 't',
                 (unsigned long)m.id, m.len);
  }
  if (!m.flags.remote) {
    for (uint8_t k = 0; k < m.len && n < 34; k++) {
      n += snprintf(out + n, sizeof out - n, "%02X", m.buf[k]);
    }
  }
  if (ch[i].timestamps) {
    n += snprintf(out + n, sizeof out - n, "%04lX", (unsigned long)(millis() % 60000u));
  }
  out[n++] = '\r';
  ch[i].port->write(out, n);
}

/* P2: if the bus only produced receive errors since the last check, try the next bit rate */
static void auto_baud(int i) {
  CAN_message_t m;
  uint8_t rec;

  if (!ch[i].open || ch[i].passive != 2 || millis() - ch[i].last_check_ms < 200u) return;
  ch[i].last_check_ms = millis();
  rec = rx_errors(i);
  if (ch[i].good_since_check == 0 && (bus_errors_seen(i) || rec != ch[i].last_rec)) {
    ch[i].auto_idx = (uint8_t)((ch[i].auto_idx + 1) % AUTO_RATES);
    ch[i].bitrate = kAutoRates[ch[i].auto_idx];
    set_rate(i);
    m.id = 0x1FFFFF00;
    m.flags.extended = true;
    m.flags.remote = false;
    m.len = 2;
    m.buf[0] = (uint8_t)((ch[i].bitrate / 1000) >> 8);
    m.buf[1] = (uint8_t)(ch[i].bitrate / 1000);
    forward(i, m);
    (void)bus_errors_seen(i);           /* discard flags raised before the switch */
    rec = rx_errors(i);
  }
  ch[i].last_rec = rec;
  ch[i].good_since_check = 0;
}

/* Accept standard AND extended frames in the RX FIFO. With CTRL2.EACEN = 0 (reset value) the
 * FlexCAN filters always compare the IDE bit, so the "accept all" filter passed only 11-bit
 * frames and every 29-bit frame was dropped silently. Setting EACEN lets the zero masks ignore
 * IDE/RTR as well. CTRL2 may only be written in freeze mode. */
static void accept_all_ids(uint32_t mcr_addr) {
  volatile uint32_t &mcr = *(volatile uint32_t *)mcr_addr;
  volatile uint32_t &ctrl2 = *(volatile uint32_t *)(mcr_addr + 0x34);
  mcr |= 0x40000000u | 0x10000000u;                      /* FRZ + HALT */
  for (uint32_t g = 0; g < 100000u && !(mcr & 0x01000000u); g++) { }   /* FRZ_ACK */
  ctrl2 |= (1u << 16);                                   /* EACEN */
  mcr &= ~0x10000000u;                                   /* leave HALT */
  for (uint32_t g = 0; g < 100000u && (mcr & 0x01000000u); g++) { }
}

/* ---- K-line bridge (third USB serial port, SerialUSB2) ----
 * ISO 9141 / ISO 14230 K-line through a UART-to-K-line level converter on Serial2
 * (pin 8 TX2 -> converter data input, pin 7 RX2 <- converter data output). The converter
 * reports the bus level on its output, so everything we transmit comes back as an echo;
 * the echo is discarded after each transmission. Message framing (format byte, addresses,
 * checksum) is left to the host (nis_kline.py) - this side only handles wire timing.
 *
 * Commands, CR terminated:
 *   V            version, reply "VK102"
 *   S            status, reply "S<line><open>": line = K-line level at idle (1 high / 0 low)
 *                read with the receive pin as a plain GPIO input, open = 1 when the UART runs
 *   N            scan: reply "N" + one character per pin 0..12, 1 when the pin reads high
 *                (the pin states are only read, nothing is reconfigured)
 *   Z            plain-GPIO test of the K-line pins, reply "Z<a><b><c><d><e>": a = receive pin
 *                level with the bus idle; b,c = its level 1 ms and 8 ms into the transmit
 *                pin being held low (a working converter pulls the bus low and reports
 *                that); d = transmit pin read back while driven low (0 = really low);
 *                e = receive pin level 1 ms after release. "Z10001" is a healthy path.
 *                The UART is re-opened afterwards.
 *   Y            terminal-label test (no rewiring): drive the pin wired to the converter's
 *                "TX" low and watch the pin wired to its "RX", reply "Y<pre><during><after>";
 *                during = 0 means "RX" is the converter's output (labels swapped)
 *   M<sec>       watch the receive pin for <sec> seconds (1..60), reply "M<idle><events><longest>"
 *                (events = low pulses, longest in tenths of a millisecond); the UART is closed
 *                meanwhile so the line can be poked by hand
 *   C            arm the hand-test latch: the receive pin becomes a plain GPIO input and
 *                every high-to-low edge on it is counted until the next command; reply
 *                "C<idle>" = the pin level at arming
 *   c            reply "c<count>" and hand the pin back to the UART (any other command
 *                does too)
 *   w            latch self-test: the Teensy pulls its own receive pin low for 1 ms;
 *                with the latch armed "c" must then count 1
 *   e            dump of the K-line UART's registers and both pads, for debugging
 *   g            for a meter: toggle the transmit pin 20 ms low / 20 ms high until the host
 *                sends a character (10 minutes at most), reply "g" when done
 *   B<baud>      UART bit rate, 300..1000000 (default 10400)
 *   P<ms>        P3: minimum pause before each transmission (default 5)
 *   W<ms>        wait for the first response byte (default 60)
 *   G<ms>        inter-byte gap that ends a response (default 23)
 *   I<hex>       fast init: bus idle for at least 300 ms, K low 25 ms, K high 25 ms,
 *                then send <hex> immediately and collect the response
 *   T<hex>       send <hex> after the P3 pause, then collect the response
 *   X<hex>       send <hex> only
 *   R            collect a response without transmitting
 *   L<ms>        listen for up to <ms>, return whatever arrives
 *   D<us>        drive K low for <us> microseconds (max 20000), then release it
 *   H<us>        wake-pulse width: hold the transmit pin low for <us> microseconds (1000..30000,
 *                default 25000) while polling the converter's output as a plain GPIO input every
 *                few microseconds; reply "H<fall>,<rise>,<edges>": fall = us from the start until
 *                the output first reads low, rise = us from the start until it reads high again
 *                (0 if never), edges = high-to-low transitions seen. A converter that passes the
 *                whole pulse gives fall ~0, rise ~<us>, edges 1; a dominant time-out cuts rise short.
 *                Sends one wake pulse onto the K-line (no message follows, so an ECU ignores it).
 *   Q            loop-back self-test: transmit a pattern, expect the converter to echo
 *                it; reply "K1" (exact echo) or "K0<hex>" (what came back instead)
 * Replies: "R<hex>" for I/T/R/L (bytes exactly as received on the wire, possibly empty),
 * "\r" for commands that have nothing to report, "E<nn>" on error:
 *   E01 no response within W, E02 bad command, E03 no response and the K-line read low
 *   before the transmission (a converter that never sees the idle line as high). */
#define KLINE_TX_PIN 8
#define KLINE_RX_PIN 7

static uint32_t k_baud = 10400;
static uint16_t k_p3 = 5, k_wait = 60, k_gap = 23;
static bool k_open = false;
static uint32_t k_last_ms;          /* end of the last K-line activity, for the P3 / 300 ms rules */
static char kline[600];             /* command line from the host */
static uint16_t klen;
static uint8_t ktx[260];
#define KRX_MAX 512
static uint8_t krx[KRX_MAX];

static void kreply(const char *s) { SerialUSB2.print(s); }
static void kerr(uint8_t code) {
  char b[6];
  snprintf(b, sizeof b, "E%02u\r", (unsigned)code);
  kreply(b);
}

/* K-line level as seen by the converter: 1 = recessive (high). The receive pin normally
 * belongs to the UART; it is switched to plain GPIO input just for the read, because a pad
 * owned by a peripheral was observed to read 0 even with 3 V on it (2026-11-23). The UART
 * keeps seeing the pad meanwhile. */
static int k_level(void) {
  volatile uint32_t *mux = portConfigRegister(KLINE_RX_PIN);
  const uint32_t saved = *mux;
  int lvl;
  *mux = 5;
  lvl = digitalRead(KLINE_RX_PIN);
  *mux = saved;
  return lvl ? 1 : 0;
}

static void kuart_open(void);

/* N: which of pins 0..12 read high; read-only, no pin is reconfigured */
static void kpin_scan(void) {
  char out[15];
  out[0] = 'N';
  for (uint8_t p = 0; p <= 12; p++) out[1 + p] = digitalRead(p) ? '1' : '0';
  out[14] = '\r';
  SerialUSB2.write(out, 15);
}

/* Z: plain-GPIO test of the K-line pins. Reply "Z<a><b><c><d><e>":
 *   a = receive pin level with the bus idle
 *   b = receive pin level 1 ms after the transmit pin is driven low
 *   c = receive pin level 8 ms into that low (a working converter has pulled the bus
 *       low and reports it: 0)
 *   d = transmit pin read back 8 ms into the low (0 when the Teensy really drives it)
 *   e = receive pin level 1 ms after the release (1)
 * "Z10001" is a healthy path. The UART is re-opened afterwards. */
static void kgpio_test(void) {
  int a, b, c, d, e;
  char out[10];
  uint32_t idle = millis() - k_last_ms;
  if (idle < 300u) delay(300u - idle);
  pinMode(KLINE_RX_PIN, INPUT);
  delay(1);
  a = digitalRead(KLINE_RX_PIN);
  pinMode(KLINE_TX_PIN, OUTPUT);
  digitalWrite(KLINE_TX_PIN, LOW);
  delay(1);
  b = digitalRead(KLINE_RX_PIN);
  delay(7);
  c = digitalRead(KLINE_RX_PIN);
  d = digitalRead(KLINE_TX_PIN);
  digitalWrite(KLINE_TX_PIN, HIGH);
  delay(1);
  e = digitalRead(KLINE_RX_PIN);
  kuart_open();
  snprintf(out, sizeof out, "Z%d%d%d%d%d\r", a, b, c, d, e);
  kreply(out);
}

static bool kparse_hex(const char *s, uint8_t *out, unsigned maxn, unsigned *n) {
  unsigned cnt = 0;
  while (s[0] && s[1]) {
    int hi = hexval(s[0]), lo = hexval(s[1]);
    if (hi < 0 || lo < 0 || cnt >= maxn) return false;
    out[cnt++] = (uint8_t)((hi << 4) | lo);
    s += 2;
  }
  if (s[0]) return false;           /* odd number of digits */
  *n = cnt;
  return true;
}

static bool kparse_num(const char *s, uint32_t *out) {
  uint32_t v = 0;
  if (!*s) return false;
  for (; *s; s++) {
    if (*s < '0' || *s > '9') return false;
    v = v * 10u + (uint32_t)(*s - '0');
    if (v > 1000000u) return false;
  }
  *out = v;
  return true;
}

/* Y: are the converter's terminals labelled from the MCU's side ("RX" = its output, "TX" =
 * its input) instead of as the listing says? Needs no rewiring. The pin wired to the "RX"
 * terminal (the UART's transmit pin) is first driven high and then left as a pulled-up
 * input, so it stays high unless the converter pulls it down. Then the pin wired to "TX"
 * is driven low. Reply "Y<pre><during><after>": during = 0 means the "RX" terminal is the
 * converter's data output and it answers a low on "TX" - the labels are swapped. */
static void klabel_test(void) {
  int pre, during, after;
  char out[8];
  uint32_t idle = millis() - k_last_ms;
  if (idle < 300u) delay(300u - idle);
  pinMode(KLINE_RX_PIN, OUTPUT);            /* pin 7, wired to the module's "TX" */
  digitalWrite(KLINE_RX_PIN, HIGH);
  pinMode(KLINE_TX_PIN, OUTPUT);            /* pin 8, wired to the module's "RX" */
  digitalWrite(KLINE_TX_PIN, HIGH);         /* charge the node high ... */
  delay(2);
  pinMode(KLINE_TX_PIN, INPUT_PULLUP);      /* ... and let the weak pull-up hold it */
  delay(1);
  pre = digitalRead(KLINE_TX_PIN);
  digitalWrite(KLINE_RX_PIN, LOW);
  delay(2);
  during = digitalRead(KLINE_TX_PIN);
  digitalWrite(KLINE_RX_PIN, HIGH);
  delay(1);
  after = digitalRead(KLINE_TX_PIN);
  kuart_open();
  snprintf(out, sizeof out, "Y%d%d%d\r", pre, during, after);
  kreply(out);
}

/* M<sec>: watch the receive pin for <sec> seconds (1..60) and report the low pulses seen.
 * The UART is closed for the duration, so the line can be poked by hand meanwhile (the
 * converter's dominant timeout makes pulses shorter than ~27 ms invisible on a meter).
 * Reply "M<idle><events><longest>": idle = level at start (1 high), events = number of
 * high-to-low edges, longest = longest low period in tenths of a millisecond (999 max). */
static void kmonitor(unsigned sec) {
  unsigned events = 0, longest;
  uint32_t low_since = 0, low_total = 0;
  int idle, last;
  char out[20];
  uint32_t t_end = micros() + (uint32_t)sec * 1000000u;
  pinMode(KLINE_RX_PIN, INPUT);
  delay(1);
  idle = last = digitalRead(KLINE_RX_PIN);
  while ((int32_t)(micros() - t_end) < 0) {
    int now = digitalRead(KLINE_RX_PIN);
    if (now != last) {
      if (now == 0) {
        events++;
        low_since = micros();
      } else {
        uint32_t d = micros() - low_since;
        if (d > low_total) low_total = d;
      }
      last = now;
    }
  }
  if (last == 0) {
    uint32_t d = micros() - low_since;
    if (d > low_total) low_total = d;
  }
  kuart_open();
  longest = (unsigned)(low_total / 100u);
  if (longest > 999u) longest = 999u;
  snprintf(out, sizeof out, "M%d%u%03u\r", idle, events, longest);
  kreply(out);
}

/* Note on this chip (learned 2026-11-23): a pad only feeds a peripheral's input while the
 * pad is actually muxed to that peripheral, and reading a pad's state with digitalRead()
 * only works while it is muxed as GPIO. So the UART cannot see a pin that is being driven
 * as a GPIO, and digitalRead() of a UART-owned pin always reads 0. Every test that pokes or
 * reads the K-line pins therefore switches the pin to GPIO first, and hands it back after. */

/* C / c: hand-test latch. While armed the receive pin is a plain GPIO input (the UART is
 * closed for the duration) and the main loop counts its high-to-low edges, i.e. every low
 * pulse on the converter's output, however short or late. "C" arms it and replies
 * "C<idle>" (the pin level at arming); "c" replies "c<count>" and hands the pin back to the
 * UART, as does any other command. Lets the line be poked by hand with no timing. */
static uint32_t k_latch_count;
static bool k_latch_armed = false;
static int k_latch_last = 1;

static void k_latch_poll(void) {
  if (!k_latch_armed) return;
  int now = digitalRead(KLINE_RX_PIN);
  if (now < k_latch_last) k_latch_count++;
  k_latch_last = now;
}

static void k_latch_arm(void) {
  pinMode(KLINE_RX_PIN, INPUT);
  k_latch_last = digitalRead(KLINE_RX_PIN);
  k_latch_count = 0;
  k_latch_armed = true;
}

static void k_latch_release(void) {
  if (!k_latch_armed) return;
  k_latch_armed = false;
  kuart_open();
}

static void kuart_open(void) {
  Serial2.begin(k_baud);
  k_open = true;
  k_last_ms = millis();
}

/* Transmit, wait for the last byte to be completely out, then drop the echo. */
static void ksend(const uint8_t *b, unsigned n) {
  Serial2.clear();
  Serial2.write(b, n);
  Serial2.flush();                  /* TX buffer and data register empty */
  delayMicroseconds(10000000UL / k_baud + 600u);   /* last byte still shifting + its echo */
  Serial2.clear();
  k_last_ms = millis();
}

/* Collect one response: first byte within k_wait, further bytes until a gap longer than
 * k_gap. Returns the byte count (0 = nothing arrived). */
static unsigned kcollect(unsigned wait_ms, unsigned gap_ms, uint8_t *buf, unsigned maxn) {
  unsigned n = 0;
  uint32_t start = micros(), last = start;
  while (n < maxn) {
    if (Serial2.available()) {
      buf[n++] = (uint8_t)Serial2.read();
      last = micros();
      continue;
    }
    if (micros() - last >= (uint32_t)(n ? gap_ms : wait_ms) * 1000u) break;
  }
  k_last_ms = millis();
  return n;
}

static void khex_out(const uint8_t *b, unsigned n) {
  char h[2];
  for (unsigned k = 0; k < n; k++) {
    h[0] = "0123456789ABCDEF"[b[k] >> 4];
    h[1] = "0123456789ABCDEF"[b[k] & 15];
    SerialUSB2.write(h, 2);
  }
}

static void khex_reply(const uint8_t *b, unsigned n) {
  SerialUSB2.write("R", 1);
  khex_out(b, n);
  SerialUSB2.write("\r", 1);
}

/* Q: loop-back self-test of the K-line path. The converter's output follows the bus, so
 * everything transmitted comes back; an exact echo proves Teensy TX -> converter -> bus ->
 * converter -> Teensy RX, and that the converter is awake. Works without the ECM. The
 * pattern cannot complete a valid frame, so an ECM on the line just discards it. */
static void kselftest(void) {
  static const uint8_t pat[] = {0x55, 0xAA, 0x00, 0xFF, 0xA5, 0x5A};
  unsigned n;
  kp3_wait();
  Serial2.clear();
  Serial2.write(pat, sizeof pat);
  Serial2.flush();
  delayMicroseconds(10000000UL / k_baud + 600u);
  n = kcollect(20, 5, krx, KRX_MAX);
  if (n == sizeof pat && memcmp(krx, pat, sizeof pat) == 0) {
    kreply("K1\r");
  } else {
    SerialUSB2.write("K0", 2);
    khex_out(krx, n);
    SerialUSB2.write("\r", 1);
  }
}

/* Wait, if needed, until at least k_p3 ms have passed since the last K-line activity */
static void kp3_wait(void) {
  uint32_t since = millis() - k_last_ms;
  if (since < k_p3) delay(k_p3 - since);
}

/* Transmit then collect the reply. <pre_level> is the K-line level read before the
 * transmission; it only decides between E01 and E03 when nothing comes back. */
static void kxchg(const uint8_t *b, unsigned n, int pre_level) {
  unsigned r;
  ksend(b, n);
  r = kcollect(k_wait, k_gap, krx, KRX_MAX);
  if (r == 0u) kerr(pre_level ? 1 : 3);
  else khex_reply(krx, r);
}

/* H<us>: measure how long the converter really holds the line low for a <us> wake pulse.
 * Both pins are plain GPIO for the duration (the UART cannot see a GPIO-driven pad anyway),
 * then the UART is re-opened. */
static void kpulse_test(uint32_t low_us) {
  char out[40];
  uint32_t t0, t, fall = 0, rise = 0, edges = 0;
  int last, now;
  bool released = false;
  uint32_t idle = millis() - k_last_ms;
  if (idle < 300u) delay(300u - idle);
  Serial2.end();
  k_open = false;
  pinMode(KLINE_RX_PIN, INPUT);
  digitalWriteFast(KLINE_TX_PIN, HIGH);
  pinMode(KLINE_TX_PIN, OUTPUT);
  delayMicroseconds(200);
  last = digitalReadFast(KLINE_RX_PIN);
  t0 = micros();
  digitalWriteFast(KLINE_TX_PIN, LOW);
  for (;;) {
    t = micros() - t0;
    if (!released && t >= low_us) {
      digitalWriteFast(KLINE_TX_PIN, HIGH);
      released = true;
    }
    if (t >= low_us + 5000u) break;
    now = digitalReadFast(KLINE_RX_PIN);
    if (now != last) {
      if (now == 0) {
        edges++;
        if (edges == 1u) fall = t;
      } else if (edges == 1u && rise == 0u) {
        rise = t;
      }
      last = now;
    }
  }
  kuart_open();
  snprintf(out, sizeof out, "H%lu,%lu,%lu\r", (unsigned long)fall, (unsigned long)rise,
           (unsigned long)edges);
  kreply(out);
}

static void khandle_line(void) {
  const char *s = kline;
  unsigned n;
  uint32_t v;

  /* any command other than the latch's own hands the receive pin back to the UART */
  if (k_latch_armed && s[0] != 'C' && s[0] != 'c' && s[0] != 'w') k_latch_release();

  switch (s[0]) {
    case 'V': kreply("VK103\r"); break;
    case 'S': {
      char b[6];
      snprintf(b, sizeof b, "S%d%d\r", k_level(), k_open ? 1 : 0);
      kreply(b);
      break;
    }
    case 'N': kpin_scan(); break;
    case 'Z': kgpio_test(); break;
    case 'Y': klabel_test(); break;
    case 'C': {
      char b[5];
      k_latch_arm();
      snprintf(b, sizeof b, "C%d\r", k_latch_last);
      kreply(b);
      break;
    }
    case 'w': {
      /* latch self-test: the Teensy pulls its own receive pin low for 1 ms (harmless: the
       * converter's output is open-drain and released at idle) and lets the armed latch see
       * it. Replies "w0" while the pin reads low; "c" must then count 1. */
      digitalWriteFast(KLINE_RX_PIN, LOW);
      pinMode(KLINE_RX_PIN, OUTPUT);
      delay(1);
      k_latch_poll();
      pinMode(KLINE_RX_PIN, INPUT);
      kreply(k_latch_last ? "w1\r" : "w0\r");
      if (!k_latch_armed) kuart_open();
      break;
    }
    case 'e': {
      /* LPUART4 (Serial2) registers and the two pads, for debugging the receive path:
       * BAUD STAT CTRL FIFO WATER PINCFG | RX mux, RX pad, TX mux, TX pad | RX select input */
      const IMXRT_LPUART_t *p = &IMXRT_LPUART4;
      char b[150];
      snprintf(b, sizeof b,
               "e%08lX %08lX %08lX %08lX %08lX %08lX | %08lX %08lX %08lX %08lX | %08lX\r",
               (unsigned long)p->BAUD, (unsigned long)p->STAT, (unsigned long)p->CTRL,
               (unsigned long)p->FIFO, (unsigned long)p->WATER, (unsigned long)p->PINCFG,
               (unsigned long)*portConfigRegister(KLINE_RX_PIN),
               (unsigned long)*portControlRegister(KLINE_RX_PIN),
               (unsigned long)*portConfigRegister(KLINE_TX_PIN),
               (unsigned long)*portControlRegister(KLINE_TX_PIN),
               (unsigned long)*&IOMUXC_LPUART4_RX_SELECT_INPUT);
      kreply(b);
      break;
    }
    case 'c': {
      char b[16];
      snprintf(b, sizeof b, "c%lu\r", (unsigned long)k_latch_count);
      k_latch_release();
      kreply(b);
      break;
    }
    case 'M':
      if (!kparse_num(s + 1, &v) || v == 0u || v > 60u) { kerr(2); break; }
      kmonitor((unsigned)v);
      break;
    case 'g': {
      /* for a meter: drive the transmit pin low for <low> ms (default 20, 1..24) and high for
       * 20 ms, until the host sends any character (or 10 minutes pass). With the pin wired
       * to the converter's input, a DC meter on the converter's LIN terminal reads the idle
       * voltage scaled by the fraction of time the line is really driven low. Reply "g". */
      const uint32_t t_end = millis() + 600000u;
      uint32_t low_ms = 20;
      if (s[1] && (!kparse_num(s + 1, &v) || v < 1u || v > 24u)) { kerr(2); break; }
      if (s[1]) low_ms = v;
      pinMode(KLINE_TX_PIN, OUTPUT);
      while (millis() < t_end && !SerialUSB2.available()) {
        digitalWriteFast(KLINE_TX_PIN, LOW);
        delay(low_ms);
        digitalWriteFast(KLINE_TX_PIN, HIGH);
        delay(20);
      }
      while (SerialUSB2.available()) (void)SerialUSB2.read();
      kuart_open();
      kreply("g\r");
      break;
    }
    case 'B':
      if (!kparse_num(s + 1, &v) || v < 300u || v > 1000000u) { kerr(2); break; }
      k_baud = v;
      kuart_open();
      kreply("\r");
      break;
    case 'P':
    case 'W':
    case 'G':
      if (!kparse_num(s + 1, &v) || v > 60000u) { kerr(2); break; }
      if (s[0] == 'P') k_p3 = (uint16_t)v;
      else if (s[0] == 'W') k_wait = (uint16_t)v;
      else k_gap = (uint16_t)v;
      kreply("\r");
      break;
    case 'I':
      if (!kparse_hex(s + 1, ktx, sizeof ktx, &n) || n == 0u) { kerr(2); break; }
      {
        uint32_t idle = millis() - k_last_ms;
        int lvl;
        if (idle < 300u) delay(300u - idle);   /* W5: bus quiet before the wake-up pattern */
        lvl = k_level();
        Serial2.end();
        k_open = false;
        pinMode(KLINE_TX_PIN, OUTPUT);
        digitalWriteFast(KLINE_TX_PIN, LOW);
        delay(25);                             /* W5: 25 ms low ... */
        digitalWriteFast(KLINE_TX_PIN, HIGH);
        delay(25);                             /* ... W6: 25 ms high */
        kuart_open();
        kxchg(ktx, n, lvl);
      }
      break;
    case 'T':
    case 'X':
      if (!kparse_hex(s + 1, ktx, sizeof ktx, &n) || n == 0u) { kerr(2); break; }
      kp3_wait();
      if (s[0] == 'X') {
        ksend(ktx, n);
        kreply("\r");
      } else {
        kxchg(ktx, n, k_level());
      }
      break;
    case 'H':
      v = 25000u;
      if (s[1] && (!kparse_num(s + 1, &v) || v < 1000u || v > 30000u)) { kerr(2); break; }
      kpulse_test(v);
      break;
    case 'Q': kselftest(); break;
    case 'R': {
      unsigned r = kcollect(k_wait, k_gap, krx, KRX_MAX);
      khex_reply(krx, r);
      break;
    }
    case 'L':
      if (!kparse_num(s + 1, &v) || v == 0u || v > 30000u) { kerr(2); break; }
      {
        unsigned r = kcollect((unsigned)v, (unsigned)v, krx, KRX_MAX);
        khex_reply(krx, r);
      }
      break;
    case 'D':
      if (!kparse_num(s + 1, &v) || v == 0u || v > 20000u) { kerr(2); break; }
      Serial2.end();
      k_open = false;
      pinMode(KLINE_TX_PIN, OUTPUT);
      digitalWriteFast(KLINE_TX_PIN, LOW);
      delayMicroseconds(v);
      digitalWriteFast(KLINE_TX_PIN, HIGH);
      kuart_open();
      kreply("\r");
      break;
    default: kerr(2); break;
  }
}

static void poll_kport(void) {
  while (SerialUSB2.available()) {
    char c = (char)SerialUSB2.read();
    if (c == '\r') {
      kline[klen] = '\0';
      if (klen) khandle_line();
      klen = 0;
    } else if (c != '\n' && klen < sizeof kline - 1) {
      kline[klen++] = c;
    }
  }
}

void setup() {
  ch[0].port = &Serial;
  ch[1].port = &SerialUSB1;
  for (int i = 0; i < 2; i++) {
    ch[i].open = false;
    ch[i].timestamps = false;
    ch[i].bitrate = 500000;
    ch[i].len = 0;
    ch[i].passive = 0;
    ch[i].listen = false;
  }
  Serial.begin(2000000);
  SerialUSB1.begin(2000000);
  SerialUSB2.begin(2000000);
  kuart_open();
  can_a.begin();
  can_a.setBaudRate(500000);
  can_a.setMaxMB(16);
  can_a.enableFIFO();
  can_a.setFIFOFilter(ACCEPT_ALL);
  accept_all_ids(IMXRT_FLEXCAN1_ADDRESS);
  can_b.begin();
  can_b.setBaudRate(500000);
  can_b.setMaxMB(16);
  can_b.enableFIFO();
  can_b.setFIFOFilter(ACCEPT_ALL);
  accept_all_ids(IMXRT_FLEXCAN2_ADDRESS);
  pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
  CAN_message_t m;
  static uint32_t led_ms;

  poll_port(0);
  poll_port(1);
  poll_kport();
  k_latch_poll();
  while (can_a.read(m)) forward(0, m);
  while (can_b.read(m)) forward(1, m);
  auto_baud(0);
  auto_baud(1);
  for (int i = 0; i < 2; i++) {
    if (hail_until_ms[i] == 0u) continue;
    if (millis() >= hail_until_ms[i] || !ch[i].open || ch[i].listen) {
      hail_until_ms[i] = 0u;
      reply(i, "hDone\r");
      continue;
    }
    uint32_t now = micros();
    bool storm_on = !hail_pulse[i] || ((millis() % 600u) < 300u);
    if (storm_on && now - hail_last_us[i] >= 110u) {
      CAN_message_t h;
      h.id = 0x7E1;
      h.len = 4;
      h.buf[0] = 0x54; h.buf[1] = 0xFF; h.buf[2] = 0x3D; h.buf[3] = 0x22;
      if (i == 0) can_a.write(h); else can_b.write(h);
      hail_last_us[i] = now;
    }
  }
  if (power_mon) {
    const uint16_t mv = (uint16_t)((analogRead(14) * 3300.0f / 1023.0f) * PWR_RATIO);
    const uint32_t now = millis();
    if (pwr_last_emit_ms == 0u ||
        (mv > pwr_last_mv + PWR_DELTA || mv + PWR_DELTA < pwr_last_mv) ||
        now - pwr_last_emit_ms >= 50u) {
      char pbuf[12];
      int n = snprintf(pbuf, sizeof pbuf, "P%u\r", mv);
      ch[0].port->write(pbuf, n);
      ch[1].port->write(pbuf, n);   /* both ports: the bridge on ACM0 drops these lines;
                                      a host logger on ACM1 can still watch (2026-11-02) */
      pwr_last_mv = mv;
      pwr_last_emit_ms = now;
    }
    uint32_t acc = 0;
    for (int k = 0; k < 32; k++) acc += analogRead(15);
    const float mv15 = (acc / 32.0f) * 3300.0f / 1023.0f;
    const int16_t ma = (int16_t)((2500.0f - (mv15 / AM_DIV)) / AM_SENS) + AM_ZERO;
    if (am_last_emit_ms == 0u ||
        (ma > am_last_ma + AM_DELTA || ma + AM_DELTA < am_last_ma) ||
        now - am_last_emit_ms >= 100u) {
      char abuf[12];
      int n = snprintf(abuf, sizeof abuf, "A%d\r", ma);
      ch[0].port->write(abuf, n);
      ch[1].port->write(abuf, n);   /* both ports: live ammeter during bridged runs */
      am_last_ma = ma;
      am_last_emit_ms = now;
    }
  }
  /* heartbeat LED: B1 = storm active (fast), otherwise slow standby blink —
     the bench can read the storm state at a glance (2026-11-03) */
  uint32_t led_iv = storm_fast ? 100u : 700u;
  if (millis() - led_ms > led_iv) {
    led_ms = millis();
    digitalWriteFast(LED_BUILTIN, !digitalReadFast(LED_BUILTIN));
  }
}
