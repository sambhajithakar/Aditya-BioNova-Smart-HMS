# Medical device support register (M8.2)

**No device model is supported yet.** A model is listed as *Validated* only
after every step of the protocol below has passed on physical hardware, with
the evidence filed here. Until then the app and the web show "No device model
has been validated on real hardware yet".

| Model | Type | Profile seen on bench | Firmware | Phones tested | Date | Result | Evidence |
|---|---|---|---|---|---|---|---|
| *(none yet)* | | | | | | | |

The candidates and the purchase proposal are in
[HARDWARE_PURCHASE_RECOMMENDATION.md](HARDWARE_PURCHASE_RECOMMENDATION.md).
Nothing has been bought.

## What has been verified without hardware

| Check | How | Result |
|---|---|---|
| Parsers for 0x2A35, 0x2A5E and 0x2A5F | 24 synthetic vectors, encoded field by field from the specifications; identical results from the Python (API) and Dart (app) parsers | ✅ automated, in CI |
| Capture → review → vitals | In-app simulator and API tests (13), Flutter tests (10), live browser E2E | ✅ automated |
| Bluetooth transport logic (live-measurement rule, stability, disconnects, permissions) | Fake BLE stack (12 Flutter tests) | ✅ automated, **no radio involved** |
| Android build, permissions and merged manifest | Release APK built; manifest inspected with aapt | ✅ |
| Behaviour with a real radio, real bonding and real devices | — | ⬜ **not done** |

The synthetic vectors prove that the two parsers agree with each other and
with this reading of the specifications. They do not prove that any real
device sends what the specification says.

## Validation protocol (per model, M8.2f)

Run it on at least 3 phones (Android 9 or 10, 12 or 13, 14 or 15), including
one entry-level phone, with the release APK under test. Record the APK's
SHA-256.

1. **Bench check**
   - Use nRF Connect.
   - The service is 0x1810 or 0x1822 and the measurement characteristic is
     present.
   - Record the Device Information values (manufacturer, model, firmware).
2. **Register and pair**
   - Register the device in the app.
   - Pairing succeeds, and the server's address check matches.
   - A different unit of the same model is refused.
3. **Twenty measurements**, taken by a clinician on synthetic test volunteers
   (staff who consent), never on patients during validation. Each reading
   must match the device's display exactly:
   - values
   - units: if the device shows kPa, the kPa text is kept and the mmHg value
     is converted
   - status icons, including movement and irregular pulse
4. **Stored memory**
   - With older readings in the device's memory, connect.
   - **None** of them is captured, and the app says how many were ignored.
5. **Reconnect** after the device sleeps, and with the phone screen locked.
6. **Offline**
   - Capture 5 readings in airplane mode for 30 minutes, then sync.
   - No reading is lost or duplicated, and each is attached to the right
     consultation.
7. **Review**
   - Accept on the web and on Android, and reject with a reason.
   - The vitals and the audit trail are correct.
8. **Permissions**
   - Deny Bluetooth permission, deny it permanently, and turn Bluetooth off.
   - Each gives a clear message, and nothing crashes.

**Pass:** every value is identical to the display, no reading is lost,
duplicated or attached to the wrong encounter, and the status flags are
shown correctly. Any failure means the model stays unsupported until fixed.

**Evidence to file:**
- the test sheet (signed by the clinician)
- screenshots
- the API audit export for the test clinic
- the APK SHA-256
- nRF Connect logs
