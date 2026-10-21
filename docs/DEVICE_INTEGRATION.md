# Medical device integration (M8.2): Bluetooth BP monitors and pulse oximeters

Status (2026-10-21): **implemented and tested with simulated devices only.**
- No physical device has been connected.
- No model is supported. The register is in [DEVICE_SUPPORT.md](DEVICE_SUPPORT.md).
- The approved plan is [M8_2_DEVICE_INTEGRATION_PLAN.md](M8_2_DEVICE_INTEGRATION_PLAN.md).

## 1. Scope and exclusions

**In scope**
- **Read-only capture of finished measurements** from devices that implement
  the standard Bluetooth SIG profiles:
  - Blood Pressure, service 0x1810: measurement 0x2A35; intermediate cuff
    pressure 0x2A36, used only as a liveness signal
  - Pulse Oximeter, service 0x1822: spot-check 0x2A5E; continuous 0x2A5F,
    captured only when stable
  - Device Information, service 0x180A
- Clinician review and acceptance on the **web and Android**.

**Excluded (initial scope)**
1. **Device control.**
   - The app never writes a characteristic.
   - It never starts an inflation or measurement.
   - It never changes a setting or a device clock, and never updates firmware.
2. **Proprietary protocols and vendor SDKs.** A device that does not expose
   the standard profile is unsupported. Nothing is reverse-engineered.
3. **Device memory download.** Record Access Control Point (0x2A52) is never
   used. Stored readings arriving on connect are ignored by the
   live-measurement rule (§4), because they could belong to someone else.
4. **Background capture.** There is no foreground service; capture runs only
   while the capture screen is open.
5. **Web Bluetooth, and other device types:** glucometers, thermometers,
   scales, ECG.
6. **Laboratory analysers** (ASTM / HL7 v2 over MLLP, the "BioNova Device
   Gateway") and DICOM. These are later milestones.
7. **Interpretation.** Values are recorded and displayed. No diagnosis or
   treatment is derived from them, and nothing is accepted automatically.

## 2. Data flow

```
device ──BLE (bonded by Android when the device requires it)──▶ Android app
  scan (0x1810 / 0x1822 only) → pair (server checks the address hash)
  capture screen, opened from a consultation (patient shown throughout)
  → phone parses for DISPLAY → device-refused readings cannot be saved
  → "Save for clinician review" → encrypted outbox (capture_id = idempotency)
        ▼  sync (waits for an offline-created consultation first)
API  POST /device-readings: re-parses the RAW bytes (authoritative) and
     checks the device, address, branch, open encounter, source and times
     → device_readings (append-only), status "pending review"
        ▼
clinician (web consultation panel, or Android review screen, online)
  ticks "belongs to <patient>, measured just now" → accept
  → normal encounter-vitals path (VitalsIn ranges, guards, audit)
  → encounter_vitals.device_reading_id; decision row (append-only)
  or reject with a reason
```

## 3. Safety rules and where each is enforced

| Rule | Enforced by |
|---|---|
| Patient context first: capture only from a consultation | Android UI. The API requires an open `encounter_id` and stores its patient |
| Only allow-listed, active devices; the device in hand must be the registered one | API: address hash and status on every reading; pairing check endpoint |
| Device bound to a branch is used only there | API: 409 |
| The server parses the raw bytes; a phone that parses differently is refused | API: `client_parsed` must equal the server's parse |
| Readings the device marks unusable are refused: ongoing, unavailable, invalid, from storage, demonstration or testing data, calibration, sensor fault | App (cannot save) and API (422, recorded in its own audit transaction) |
| Stored or old readings replayed on connect are never captured | App: live-measurement rule (§4) |
| Capture time is plausible (not in the future, not older than 72 h); device clock skew is flagged and shown | API |
| Simulated data never reaches a production record | Production refuses to start with `DEVICE_SIMULATOR_ENABLED`; simulator devices and readings are refused when it is off; a SIMULATED badge is shown; "SIMULATED" is written in the vitals note |
| Never accepted automatically; one decision per reading | API: explicit accept with `confirm_patient`; advisory lock plus unique index |
| Accepting needs `device.review` and `encounter.write`; the encounter must be open; values within `VitalsIn` ranges (refused, never clipped) | API |
| Raw payload, its hash, source, times, device, capturer and app version kept forever | `device_readings` is append-only (trigger, no grants) |
| Every step audited; reads audited as `phi.read` | API |

## 4. The live-measurement rule (wrong-patient protection)

Many BP monitors replay their memory as indications when a phone connects.
The Bluetooth layer takes a measurement only if:
- the device does not mark it as stored, **and**
- its time stamp is within 10 minutes of the phone's clock, **or**, when it
  has no usable time stamp, a BP measurement arrives after
  intermediate-cuff-pressure updates on the same connection.

In addition:
- repeated indications are dropped
- malformed notifications are ignored
- continuous SpO2 needs 5 stable samples

If nothing live arrives, the timeout message says how many readings were
ignored. This rule is implemented and unit-tested; whether real devices
behave this way is part of the hardware validation.

## 5. Components

| Layer | Files |
|---|---|
| Specification parsers (authoritative) | `apps/api/app/devices/gatt.py` |
| Parsers (display) | `apps/mobile/lib/devices/gatt.dart` |
| Shared synthetic vectors | `packages/contracts/device_vectors.json` (generated by `scripts/generate_device_vectors.py`; CI checks it is current) |
| Database | migration `0019`: `medical_devices`, `device_readings`, `device_reading_decisions`, `encounter_vitals.device_reading_id` |
| API | `apps/api/app/routers/devices.py` (feature `medical_devices`) |
| Android | `lib/devices/` (transport, simulator, BLE, live filter, device book); screens `devices_screen`, `device_capture_screen`, `device_review_screen` |
| Web | consultation panel `components/DeviceReadings.tsx`; `/settings/devices` |

**Permissions**

| Permission | Roles |
|---|---|
| `device.read` | owner, admin, doctor, nurse |
| `device.manage` | owner, admin |
| `device.capture` | owner, doctor, nurse |
| `device.review` | owner, doctor, nurse; acceptance also needs `encounter.write` |

**Android permissions**
- Android 12+: `BLUETOOTH_SCAN` (`neverForLocation`) and `BLUETOOTH_CONNECT`.
- Location is requested only up to Android 11, where BLE scanning needs it.
  The plugin's broader location request is stripped from the merged manifest.
- Bluetooth and location hardware are optional.
- Permissions are asked for only when device pairing or capture is opened.

**Simulator**
- Four virtual devices: `SIM-0000B001`/`B002` (BP) and `SIM-0000A001`/`A002`
  (SpO2).
- Seven scenarios: normal; high BP with irregular pulse and movement; device
  clock not set; low SpO2; a stored record (refused); an invalid measurement
  (refused).
- Compiled into debug builds and the demo APK
  (`--dart-define=HMS_DEVICE_SIMULATOR=true`).
- The API accepts simulator data only in development or test.

## 6. Adding a device model (after the owner approves its purchase)

1. Bench-check it and run the protocol in DEVICE_SUPPORT.md.
2. Capture its real payloads, with no patient data: synthetic volunteers'
   readings only, with consent. Add them as named vectors next to the
   synthetic ones.
3. Fix any parser divergence in **both** parsers.
4. Record the result in DEVICE_SUPPORT.md. Only then may the model be
   described as supported.

## 7. Regulatory and privacy notes

- BP monitors and pulse oximeters are medical devices in India, and their own
  approvals are the makers'.
- This software transfers, stores and displays readings for clinician
  review. It adds no interpretation beyond range validation.
- A regulatory consultant should confirm the software's classification (CDSCO)
  before any commercial claim.
- Device readings are health data under the DPDP Act 2023. Consent, purpose
  and retention follow the clinic's existing policy.
- Bluetooth addresses are stored only as per-tenant hashes.
