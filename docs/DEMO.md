# Demo guide: Aditya BioNova Smart HMS (synthetic data only)

This guide runs the complete existing software, the **web application** and
the **Android app**, on your own computer and phone. Nothing is deployed to
the internet. No money moves, no message is sent and no medical hardware is
needed.

> **Never enter real patient data in the demo.** It runs in development
> mode over plain HTTP on your Wi-Fi, with throw-away passwords. Every
> clinic, patient, phone number and device in it is invented.

What is real and what is simulated, module by module:
[MODULE_STATUS.md](MODULE_STATUS.md).

## 1. What you need

- A Windows, macOS or Linux computer with **Docker Desktop** (free for
  personal and small-business use): <https://www.docker.com/products/docker-desktop/>.
  The computer needs about 4 GB of free memory and 10 GB of disk.
- The code from the development branch `claude/pensive-albattani-n0zcba`.
  Either:
  - `git clone -b claude/pensive-albattani-n0zcba https://github.com/sambhajithakar/Aditya-BioNova-Smart-HMS.git`, or
  - on GitHub, switch to that branch and choose **Code → Download ZIP**,
    then unzip it.
- For the Android part: an Android phone (Android 8 or newer) on the **same
  Wi-Fi** as the computer, and the demo APK
  `aditya-bionova-hms-LAN-DEMO.apk` (section 3).

## 2. Start the demo server (web + API)

Open a terminal in the project folder and run:

| Computer | Command |
|---|---|
| Windows (PowerShell) | `powershell -ExecutionPolicy Bypass -File scripts\demo-up.ps1` |
| macOS / Linux | `scripts/demo-up.sh` |

The first start builds the images, which takes about 5–10 minutes. Later
starts take under a minute. When it is ready, the script prints, for example:

```
Aditya BioNova Smart HMS demo is running (SYNTHETIC DATA ONLY).
  On this computer:   http://localhost:3000
  From your phone:    http://192.168.1.20:3000   (web)
  Android demo app:   server address 192.168.1.20:8000
```

- **Web demo:** open `http://localhost:3000` on the computer, or the
  `http://<address>:3000` link in the phone's browser.
- If the script lists more than one address, use the one of your Wi-Fi
  adapter. It usually starts with `192.168.`.
- **Windows firewall:** if the phone cannot connect, allow Docker Desktop
  (or TCP ports 3000 and 8000) for *Private* networks:
  Windows Security → Firewall & network protection → Allow an app through
  firewall. Make sure your Wi-Fi is set as a *Private* network.

Stop and reset:

| Command | Effect |
|---|---|
| `scripts/demo-up.sh down` (or `demo-up.ps1 down`) | Stops the demo and keeps the data |
| `scripts/demo-up.sh reset` (or `demo-up.ps1 reset`) | Stops the demo and **deletes** the demo data |
| Start the demo again | A fresh copy is re-seeded |

## 3. Install the Android demo app

The demo APK is a special **LAN demo build**:
- It asks for the address of the demo server on your computer.
- It shows a red **DEMO · synthetic data only** strip on every screen.
- It includes the Bluetooth device **simulator**.
- It is signed with the Android debug certificate. It is for this
  evaluation only and must never be distributed.

1. Copy `aditya-bionova-hms-LAN-DEMO.apk` to the phone, by USB, e-mail to
   yourself or Google Drive.
2. Check the file's SHA-256 against the value you were given (section 8).
3. On the phone, open the file. Android asks to allow installs from that
   app, such as Files or Chrome: allow it for this install.
4. Google Play Protect may warn that the app is from an unknown developer.
   That is expected for a debug-signed demo. Choose **Install anyway**.
5. Open **Aditya BioNova HMS**. On the *Demo server* screen, type the
   address printed by the script, for example `192.168.1.20:8000`, and tap
   **Connect**.
   - The app checks that the server is an HMS demo server.
   - It refuses any server that reports a production environment.
   - It accepts plain `http://` only for private Wi-Fi addresses.
6. Sign in with a demo account (section 4). On first sign-in the app asks
   you to set a 4–6 digit PIN for this phone.

Changing the server later: on the sign-in screen, tap **Change demo server**.
This deletes the app's local data on the phone.

To remove the app: long-press its icon → Uninstall.

## 4. Demo accounts

The password for every account is `Demo-Sunrise-2026!`

| Clinic (edition) | Accounts |
|---|---|
| **Sunrise Demo Clinic** (Clinic Plus + AI) | `owner@`, `admin@`, `doctor@`, `nurse@`, `receptionist@`, `pharmacist@`, `labtechnician@`, `billing@`, `auditor@` + `sunrise-demo.example.com` |
| **BioNova Demo Hospital** (Hospital Advanced: IPD, beds) | `owner@`, `doctor@`, `nurse@`, `receptionist@`, `pharmacist@`, `labtechnician@`, `billing@` + `demo-hospital.example.com` |
| **Gram Arogya Rural Clinic** (Rural Clinic edition) | `owner@rural-demo.example.com`, `doctor@rural-demo.example.com` |
| **Platform console** (vendor) | `platform@aditya-bionova.example.com` |

Each clinic comes seeded with:
- 8 synthetic patients
- tomorrow's appointments
- a waiting OPD queue
- paid invoices
- pharmacy stock (Sunrise and Hospital)
- one admission (Hospital)
- **two simulated Bluetooth devices**
- **an open consultation for Lata Gaikwad**, with a simulated BP reading
  and a simulated SpO2 reading **waiting for clinician review**

## 5. Guided demonstration (web)

Use a computer browser at `http://localhost:3000`. The language buttons
(English / मराठी / हिंदी) are at the top.

| # | Sign in as | Do this | What you should see |
|---|---|---|---|
| 1 | `receptionist@sunrise-demo…` | **Patients** → fill name, gender, phone → *Register patient* | A notice with the new UHID |
| 2 | (same) | **Appointments** → search the new patient, pick a date, time and reason → *New appointment* | The appointment in the list |
| 3 | (same) | **Queue** → pick the patient → *Add to queue* | A token number in today's queue |
| 4 | `doctor@sunrise-demo…` | **Consultation** → *Open consultations* → "Giddiness since morning (demo)" | Lata Gaikwad's consultation |
| 5 | (same) | Under **Device readings to review**: tick "This reading belongs to Lata Gaikwad…" on the BP reading → *Accept into vitals* | Two **SIMULATED** readings first; after accepting, BP 120/80 appears in the vitals table |
| 6 | (same) | On the SpO2 reading: type a reason → *Reject* | "Reading rejected." Nothing is accepted without a clinician; a reject needs a reason |
| 7 | (same) | **Prescribe**: tap *+ Amlodipine 5 mg*, enter dose, route, frequency, days, quantity → *Sign prescription* → *Print Rx* | A printable prescription with prescriber and clinic. Signing with an empty dose is refused |
| 8 | `billing@sunrise-demo…` | **Billing** → pick Lata Gaikwad → line "OPD consultation", price → *New invoice* → *Issue* → *Take payment* | The invoice status moves draft → issued → paid; *Receipt* prints. The payment is **recorded** only; no gateway is involved |
| 9 | `pharmacist@sunrise-demo…` | **Pharmacy** → *Signed prescriptions* → Lata Gaikwad → *Dispense* | "Dispense ✓ Amlodipine 5 mg × 30" and the stock falls 200 → 170 |
| 10 | `owner@sunrise-demo…` | **Settings → Medical devices** | The simulated devices; the notice says no real model is validated |
| 11 | `owner@rural-demo…` | Sign in on the **phone's browser** | The Rural Clinic edition, phone layout with bottom navigation; no Pharmacy or Laboratory (edition gating) |
| 12 | any | Turn the computer's Wi-Fi off for a moment on the Billing page | A red offline banner; payment buttons are disabled until the connection returns. The web app does **not** save offline (the Android app does) |
| 13 | `owner@demo-hospital…` | **IPD** | Wards, beds and the seeded admission |
| 14 | `owner@sunrise-demo…` | **Copilot**, **Reports**, **Communications** | The Copilot answers from the clinic's own figures (template answers, no AI model). Communications shows the **mock outbox**: nothing is sent |
| 15 | `platform@aditya-bionova…` | **Platform** | Tenants, editions, support. Prices are empty until you set them |

## 6. Guided demonstration (Android)

On the phone, after connecting to the demo server (section 3):

| # | Sign in as | Do this | What you should see |
|---|---|---|---|
| 1 | `doctor@sunrise-demo…` | Sign in → set a PIN | The Queue tab, status chip "Online" |
| 2 | (same) | **Consult** → the draft for Lata Gaikwad → *Measure with device* | "Measuring for: Lata Gaikwad", the **SIMULATED** BP monitor and a scenario list (normal, high and irregular, no clock, …) |
| 3 | (same) | First pair the simulated device if asked: menu ⋮ → *Medical devices* → *Pair* next to "Simulated BP monitor (demo)". Then *Start measurement* → *Save for clinician review* | "Not yet part of the record — a clinician must accept it." The reading waits in the outbox |
| 4 | (same) | *Review device readings* | Pending readings with Accept (needs the patient confirmation tick) and Reject (needs a reason) |
| 5 | (same) | **Offline:** turn on **airplane mode** → **Queue** → pick a patient → *Add to queue (works offline)*; **Rx** → make a draft → *Save draft (works offline)* | Status "Offline". Items wait in **Sync** ("Pending sync") |
| 6 | (same) | Turn airplane mode off → **Sync** → *Sync now* | The pending items go to the server. Check them on the web (Queue / Consultation) |
| 7 | (same) | Menu ⋮ → **Rural Clinic mode** on | Large buttons and text, simplified steps, quick-pick frequency and days chips |
| 8 | (same) | Language button (文A) → मराठी or हिंदी | The app in Marathi or Hindi |
| 9 | `receptionist@sunrise-demo…` | **Register**, **Billing** | Role-based tabs: no Consult or Rx for reception |

## 7. What the demo does not show

The following are not demonstrated; see [MODULE_STATUS.md](MODULE_STATUS.md):

| Area | Status |
|---|---|
| Real Bluetooth devices | No device has been bought or tested. The real Bluetooth code exists but is **not tested** |
| Real e-mail, SMS and WhatsApp delivery | Mock outbox only |
| Real payments | Simulator only. Live payments are refused |
| AI language models, speech recognition | Mock or rule-based engines only |
| Pharmacy sale invoices, IPD billing, OT, ER, TPA, ABDM / FHIR | Not built |

## 8. Files

The demo APK is **not** stored in the repository. It is provided alongside
this guide.

| Item | Value |
|---|---|
| File | `aditya-bionova-hms-LAN-DEMO.apk` (about 77 MB, universal) |
| Build command | `HMS_ALLOW_DEBUG_SIGNING=1 flutter build apk --release --dart-define=HMS_DEMO_LAN=true --dart-define=HMS_DEVICE_SIMULATOR=true` |
| Signature | Android debug certificate |

Ordinary builds without `HMS_DEMO_LAN` are unchanged: fixed server and
HTTPS only.
