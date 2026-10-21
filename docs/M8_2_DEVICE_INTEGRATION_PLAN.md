# M8.2 — Bluetooth BP monitors and pulse oximeters: implementation plan

> **Status: PROPOSED. Awaiting the owner's approval. No M8.2 code has been
> written.** This plan does not claim that any device is supported. A device
> is listed as supported only after it has been validated on physical
> hardware (§8).

## 1. Scope

**In scope**
- The Android app reads finished measurements from Bluetooth Low Energy (BLE)
  devices that implement the **standard Bluetooth SIG profiles**:
  - Blood Pressure (BLS)
  - Pulse Oximeter (PLX)
- A built-in **simulator** with synthetic readings, so the whole pipeline can
  be developed and tested without hardware.
- Readings go through the existing encrypted offline outbox to the API. They
  wait **pending clinician review**.
- Only on acceptance are they written to the encounter's vitals, through the
  existing validation.

**Out of scope for M8.2 (later milestones)**
- Anything that controls a device: starting a cuff inflation, changing
  settings, firmware updates. Acquisition is **read-only**.
- Vendor-proprietary protocols. A device that does not expose the standard
  profile is not supported. Nothing is reverse-engineered.
- Devices' stored-record download (Record Access Control Point, 0x2A52).
  Only measurements taken while the app is connected are used, so old readings
  in a device's memory cannot be attached to the wrong patient. This can be
  revisited later with explicit per-record mapping.
- Web Bluetooth, glucometers, thermometers, weighing scales, ECG.
- Wired lab analysers (ASTM / HL7 v2 over MLLP) through a "BioNova Device
  Gateway". These are listed in §10 as a later milestone.
- Autonomous interpretation. The app records and displays values; it draws no
  diagnosis from them.

## 2. Standards the parsers implement

Written from the Bluetooth SIG specifications and assigned numbers (the
current Blood Pressure and Pulse Oximeter service specifications and the GATT Specification Supplement; versions are pinned in M8.2a). No vendor code is
copied.

| Service | UUID | Characteristics used |
|---|---|---|
| Blood Pressure | 0x1810 | Blood Pressure Measurement **0x2A35** (indicate); Intermediate Cuff Pressure 0x2A36 (notify, shown live only, never stored); Blood Pressure Feature 0x2A49 (read) |
| Pulse Oximeter | 0x1822 | PLX Spot-Check Measurement **0x2A5E** (indicate); PLX Continuous Measurement **0x2A5F** (notify); PLX Features 0x2A60 (read) |
| Device Information | 0x180A | Manufacturer Name 0x2A29, Model Number 0x2A24, Serial 0x2A25, Firmware 0x2A26 (read, for the device register) |
| Current Time | 0x1805 | 0x2A2B (read only, to detect clock skew; never written) |

**Blood Pressure Measurement (0x2A35).** A flags byte, then:
1. systolic, diastolic and mean arterial pressure (SFLOAT each)
2. a time stamp (7 bytes), if present
3. pulse rate (SFLOAT), if present
4. user ID (uint8), if present
5. measurement status (uint16), if present

The flags byte says which optional fields are present:
- bit 0: units (mmHg or kPa)
- bit 1: time stamp
- bit 2: pulse rate
- bit 3: user ID
- bit 4: measurement status

kPa is converted to mmHg (×7.50062) and rounded, and the original value is
kept. These status bits are shown to the clinician, never hidden:
- body movement
- cuff fit
- irregular pulse
- pulse-rate range
- measurement position

**PLX Spot-Check (0x2A5E).** A flags byte, then:
1. SpO2 and pulse rate (SFLOAT each)
2. a time stamp, if present
3. measurement status (uint16), if present
4. device and sensor status (24-bit), if present
5. pulse amplitude index, if present

The flags byte says which optional fields are present, and whether the
device clock is not set.

**PLX Continuous (0x2A5F).**
- Fields: the Normal SpO2PR pair, then optional Fast and Slow pairs, status
  fields and pulse amplitude index.
- Only a value the clinician *captures* (a "take reading" button after the
  signal is stable for a few seconds) becomes a reading; the live stream is
  never stored.

**SFLOAT.** A 4-bit signed exponent and a 12-bit signed mantissa. The special
values are recognised and never turned into numbers:
- NaN 0x07FF
- NRes 0x0800
- +INF 0x07FE
- −INF 0x0802
- reserved 0x0801

A reading containing one is rejected with a clear message.

## 3. Architecture

```
BLE device ──(standard GATT, bonded)──▶ Android app
  lib/devices/ble_adapter.dart     plugin wrapper (scan filtered by service UUID, connect, subscribe)
  lib/devices/parsers/*.dart       pure Dart parsers (0x2A35, 0x2A5E, 0x2A5F, SFLOAT, DateTime)
  lib/devices/simulator.dart       synthetic peripheral emitting spec-correct byte vectors (dev/demo builds)
  lib/devices/capture_screen.dart  patient/encounter chosen FIRST → measure → review values + status → save
        │  outbox op (encrypted at rest, idempotency key = SHA-256 of raw bytes + device + encounter)
        ▼
API  POST /device-readings  ─▶ device_readings (append-only, status = pending_review)
     GET  /encounters/{id}/device-readings
     POST /device-readings/{id}/accept ─▶ existing encounter-vitals path and VitalsIn validation
     POST /device-readings/{id}/reject  (reason required)
        ▼
Web consultation screen: "Device readings awaiting review" panel (accept / reject)
```

### Safety rules (enforced server-side, tested)

1. **Patient context first.**
   - The capture screen opens only from an open encounter, or after choosing
     a patient.
   - A reading always carries `encounter_id`. Nothing is auto-attached by
     time or by device.
2. **Review before it becomes record.**
   - Readings land as `pending_review`.
   - Acceptance writes vitals through the existing encounter update, with
     its guards, audit event and `VitalsIn` ranges. An out-of-range value is
     refused, not clipped.
   - For IPD nursing records, the existing rule that SpO2 below 85 needs an
     escalation note applies unchanged.
3. **Provenance kept.** Each reading stores:
   - the raw payload (hex) and its SHA-256
   - the parsed values and units
   - device time and received time, plus a clock-skew flag when they differ
     by more than 10 minutes or the device clock is "not set"
   - source: `ble`, `simulator` or `manual`
   - the device register id, the app user, and the app version
4. **Simulator readings are labelled.**
   - They are refused by the API outside development and test, unless the
     tenant is a demo tenant.
   - They are always shown with a "SIMULATED" badge.
5. **Tenant allow-list.**
   - A device must be registered by an administrator (`device.manage`) and
     bonded before its readings are accepted.
   - Unknown or retired devices get 403.
6. **Append-only.**
   - `device_readings` and `device_reading_decisions` have no UPDATE or DELETE
     grant, and a trigger enforces this.
   - The pending → accepted/rejected state is the latest decision row.
   - RLS uses the strict `organization_id = GUC` policy, like every tenant
     table.

### Data model (migration 0019, proposed)

- `medical_devices`:
  - `organization_id`, `branch_id`
  - `kind` (`bp_monitor` | `pulse_oximeter`)
  - manufacturer, model, serial, firmware (from Device Information)
  - `ble_address` (hashed, never shown)
  - `registered_by`, `status` (`active` | `retired`), `validated_model` (FK
    to the validated-models list, §8)
- `device_readings` (append-only):
  - `organization_id`, `encounter_id`, `patient_id`, `device_id`
  - `kind`, `values` (JSONB with units), `status_flags` (JSONB)
  - `raw_hex`, `raw_sha256` (unique per tenant, for idempotency)
  - `device_time`, `received_at`, `clock_skew`
  - `source`, `captured_by`, `app_version`
- `device_reading_decisions` (append-only): `reading_id`, `decision`
  (`accepted` | `rejected`), `reason`, `decided_by`, `vitals_ref`.
- New permissions:
  - `device.manage` (owner, admin)
  - `device.capture` (doctor, nurse)
  - accept and reject reuse `encounter.write`

### Android specifics

- **Permissions:**
  - Android 12 and later: `BLUETOOTH_SCAN` (with
    `android:usesPermissionFlags="neverForLocation"`) and `BLUETOOTH_CONNECT`
  - Android 11 and earlier: `BLUETOOTH`, `BLUETOOTH_ADMIN` and
    `ACCESS_FINE_LOCATION`, each with `maxSdkVersion="30"`
  - The permission prompt is shown only when the user opens device capture.
- **No foreground service in M8.2.** Capture runs only while the capture
  screen is open. If background capture is ever needed, Android 14 requires
  the `connectedDevice` foreground-service type, and that would be a separate
  decision.
- **Security:**
  - Bonding is required: the PLX profile mandates security mode 1 level ≥ 2.
  - LE Secure Connections are used where the device supports them.
- **Reliability:**
  - Reconnect with backoff.
  - Duplicate indications are dropped by `raw_sha256`.
  - Dependent outbox ordering: the reading waits for its encounter if the
    encounter was created offline.
- **BLE plugin:**
  - Proposed: `flutter_reactive_ble`, BSD-3-Clause, subject to a licence and
    maintenance check before adoption.
  - `flutter_blue_plus` is **not** proposed until its current licence terms
    for commercial use are verified.
  - The licence is recorded in LICENSES.md and on the in-app licence screen.

## 4. Work packages (each a separate, tested commit series)

| # | Package | Needs hardware? |
|---|---|---|
| M8.2a | Dart parsers, the SFLOAT and date-time codec, and synthetic byte-vector test suites for every flag combination and special value | No |
| M8.2b | Migration 0019, API endpoints, RLS, the append-only triggers, idempotency, accept through VitalsIn, permissions, and API tests | No |
| M8.2c | In-app simulator, device register UI, capture screen (en/mr/hi), and outbox integration. Flutter tests through a fake BLE adapter | No |
| M8.2d | BLE adapter on the chosen plugin, Android permissions, bonding flow, and reconnect handling | Compiles and is unit-tested without hardware; behaviour **unverified** until M8.2f |
| M8.2e | Web review panel on the consultation screen, plus E2E (simulator source) | No |
| M8.2f | **Hardware validation** on purchased devices and phones (§8). docs/DEVICE_SUPPORT.md lists only validated models | **Yes** |

M8.2a–e can be completed and demonstrated with the simulator. Until M8.2f
passes for a model, every screen and document says "not yet validated on
hardware".

## 5. Tests

- **Parsers:**
  - spec-derived vectors for each flag bit, kPa vs mmHg, all SFLOAT specials
  - truncated or oversized payloads
  - device-clock-not-set
  - status bits for body movement, cuff loose and irregular pulse
- **API:**
  - idempotent replay
  - cross-tenant RLS at the database
  - append-only grants and trigger
  - unknown or retired device → 403
  - simulator reading refused in production settings
  - accept writes vitals and is audited
  - an out-of-range value is refused on accept
  - double accept → 409
  - reject needs a reason
- **Flutter:**
  - capture without a patient context is impossible
  - offline capture and sync
  - duplicate indication suppressed
  - permission-denied paths
  - the simulator badge is shown
- **Web E2E:** a simulated reading appears in the consultation; the clinician
  accepts it; the vitals are updated.

## 6. Documentation to be delivered

- docs/DEVICE_INTEGRATION.md: architecture, data flow, safety rules, and how
  to add a model.
- docs/DEVICE_SUPPORT.md, with the columns: model, profile, firmware, phones
  tested, date, result, evidence.
- An update to the privacy notice (device data categories), the DPIA and
  LICENSES.md.

## 7. Regulatory notes (to confirm with a consultant; not legal advice)

- BP monitors and pulse oximeters are medical devices in India (CDSCO). The
  devices' own approvals are the manufacturers' responsibility.
- Software that only transfers, stores and displays readings for clinician
  review is lower risk. Software that interprets them can itself become
  regulated software. M8.2 adds no interpretation beyond the existing range
  validation.
- A regulatory consultant should confirm this classification before any
  commercial claim. The DPDP Act 2023 obligations (consent, purpose
  limitation, retention) apply to the readings like any other health data.

## 8. Hardware validation (M8.2f) — needs the owner's purchase approval

**Candidates to evaluate.** These are claims to verify, not support
statements.

| Type | Model | Why | Profile status |
|---|---|---|---|
| BP | A&D UA-651BLE | Marketed with Continua / Bluetooth SIG BLS | to verify |
| BP | Omron HEM-7361T or HEM-7143T1 | Common in India | **Unverified**: may need Omron's proprietary SDK (agreement) → would be out of scope |
| SpO2 | Nonin 3230 | Documents the SIG PLX profile | to verify |
| SpO2 | Beurer PO 60 | Available in India | **Unverified** |

- **Phones:** 3–4 Android phones on Android 9–15, including one entry-level
  device with 2 GB of RAM.
- **Optional:** an nRF52840 USB dongle (about US$11) with Nordic's open
  tools, to emulate a standard peripheral for repeatable tests.
- **Protocol per model:**
  - 20 measurements, each compared with the device's own display (values,
    units, status flags)
  - bonding, reconnect after the device sleeps, and phone screen-lock
  - 30 minutes of airplane mode followed by sync
  - recorded per run: firmware, phone, Android version and APK SHA-256
- **Pass criteria:**
  - every value identical to the display
  - zero readings lost or duplicated
  - zero readings attached to the wrong encounter
  - status flags shown correctly

## 9. Decisions needed from the owner

1. Approve this plan and the work-package order (a → f).
2. Approve the BLE plugin choice, after the licence check (`flutter_reactive_ble`
   proposed).
3. Approve the hardware purchase list and budget for M8.2f. Prices will be
   quoted before buying; no money will be spent without approval.
4. Confirm the scope exclusions: no device memory download, no foreground
   service, no device control, and no proprietary protocols.
5. Who may accept device readings: clinicians on the web only, or also
   doctors on Android?

## 10. Later (not M8.2)

- Glucometers (Glucose 0x1808 with RACP), thermometers (0x1809), weight
  scales (0x181D).
- A BioNova Device Gateway for laboratory analysers: ASTM E1381/E1394
  (CLSI LIS1/LIS2) and HL7 v2 ORU^R01 over MLLP.
- DICOM, and SCP-ECG (ISO 11073-91064).
- Each would need its own plan, its own hardware validation and the owner's
  approval.
