// AUTO-GENERATED from src/d2diag/signals/td5.json by tools/gen_signal_header.py.
// DO NOT EDIT. Regenerate: python3 tools/gen_signal_header.py
// The ESP decode table is derived from the signal store so the two never drift.
// Requires `enum Kind { U8, U16, S16 };` and `struct Field { … };` before include.

static const Field FIELDS[] = {
  { "rpm", 0x09,  0, U16,          1.0f,       0.0f },
  { "speed", 0x0D,  0, U8 ,          1.0f,       0.0f },
  { "battery", 0x10,  0, U16,        0.001f,       0.0f },
  { "coolant_c", 0x1A,  0, U16,          0.1f,    -273.2f },
  { "air_c", 0x1A,  4, U16,          0.1f,    -273.2f },
  { "fuel_c", 0x1A, 12, U16,          0.1f,    -273.2f },
  { "throttle_v", 0x1B,  0, U16,        0.001f,       0.0f },
  { "map_bar", 0x1C,  0, U16,       0.0001f,       0.0f },
  { "maf", 0x1D,  4, U16,          0.1f,    -515.0f },
  { "inj_mg", 0x1D,  6, U16,         0.01f,       0.0f },
  { "egr_pct", 0x1D, 15, U8 ,  0.392156863f,       0.0f },
  { "wastegate_pct", 0x1D, 17, U8 ,  0.392156863f,       0.0f },
  { "rpm_error", 0x21,  0, S16,          1.0f,       0.0f },
  { "ambient_bar", 0x23,  0, U16,       0.0001f,       0.0f },
  { "balance_1", 0x40,  0, S16,          1.0f,       0.0f },
  { "balance_2", 0x40,  2, S16,          1.0f,       0.0f },
  { "balance_3", 0x40,  4, S16,          1.0f,       0.0f },
  { "balance_4", 0x40,  6, S16,          1.0f,       0.0f },
  { "balance_5", 0x40,  8, S16,          1.0f,       0.0f },
};
static const size_t NFIELDS = sizeof FIELDS / sizeof FIELDS[0];

// Unique LIDs to read each cycle (derived from FIELDS above).
static const uint8_t LIDS[] = { 0x09, 0x0D, 0x10, 0x1A, 0x1B, 0x1C, 0x1D, 0x21, 0x23, 0x40 };
static const size_t  NLIDS  = sizeof LIDS / sizeof LIDS[0];
