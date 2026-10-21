# M8.2f hardware purchase recommendation (for approval)

> **Nothing has been purchased.** Buying anything needs the owner's explicit
> approval. Prices are **indicative**, from public listings found on
> 2026-10-21; they change often and must be re-quoted before ordering.
> "Candidate" means the model is worth testing. It does **not** mean the
> model works with Aditya BioNova Smart HMS. Support is claimed only after
> the validation protocol in [DEVICE_SUPPORT.md](DEVICE_SUPPORT.md) passes.

## 1. What the software needs from a device

The app reads only the **standard Bluetooth SIG profiles**:
- Blood Pressure Service 0x1810, with Blood Pressure Measurement 0x2A35
- Pulse Oximeter Service 0x1822, with spot-check 0x2A5E or continuous 0x2A5F

Devices that send their data only through a vendor's own app or protocol
cannot be used. They are out of scope, and they will not be reverse-engineered.

Public product pages rarely state the GATT services a device exposes. The
first step for every candidate is therefore a **bench check before buying in
quantity**:
1. Buy one unit.
2. Run Nordic's free *nRF Connect for Mobile* on an Android phone.
3. Check that the 0x1810 or 0x1822 service is advertised and that one
   measurement arrives on 0x2A35 or 0x2A5E/0x2A5F.

If it is not, the unit is returned or written off, and the model is recorded
as "not compatible".

## 2. Candidates

### Blood pressure monitors

| Model | Why it is a candidate | Standard-profile status | Indicative price (India) | Source |
|---|---|---|---|---|
| **A&D Medical UA-651BLE** | Marketed by A&D as a Continua-certified Bluetooth LE monitor. Continua's Bluetooth LE interface is built on the SIG health profiles | **Unconfirmed**: verify on the bench | No Indian listing found. US listing for the wide-cuff variant: US$49.99. The non-Bluetooth UA-651 is about ₹2,400 in India | [A&D product page](https://asia.aandd.jp/product/ua-651ble/), [A&D BLE series](https://aandd.jp/products/medical/consumer/ble_series.html), [Walmart listing](https://www.walmart.com/c/kp/ua-1328), [PriceDekho UA-651](https://www.pricedekho.com/blood-pressure-monitors/ad-upper-arm-bpm-ua-651-price-pjfCFN.html) |
| **Omron HEM-7361T** | Widely sold in India and clinically familiar | **Unconfirmed, likely proprietary**: documented only with the OMRON connect app. If it does not expose 0x1810 it is out of scope (an Omron SDK would need a commercial agreement) | ₹4,800–5,200 (MRP ₹7,290) | [PharmEasy](https://www.pharmeasy.in/health-care/products/omron-hem-7361t-bluetooth-digital-blood-pressure-monitor-for-clinical-professional-use-3920838), [Smartprix](https://www.smartprix.com/bp_monitors/omron-brand), [OMRON connect](https://omronconnect.com/bd/en_gb/products) |

### Pulse oximeters

| Model | Why it is a candidate | Standard-profile status | Indicative price | Source |
|---|---|---|---|---|
| **Nonin 3230** (Bluetooth LE) | Clinical-grade finger oximeter built for integration (OEM). Nonin describes Bluetooth LE spot-checks with automatic pairing | **Unconfirmed**: verify on the bench | No retail price is published; it is sold through partners. Resale listings of US$13–26 are not a suitable source for clinical validation units, so **request a distributor quote** | [Nonin 3230](https://www.nonin.com/products/3230/), [MobiHealthNews](https://www.mobihealthnews.com/news/nonin-debuts-bluetooth-4-pulse-oximeter), [HospiMedica](https://www.hospimedica.com/critical-care/articles/294750263/power-efficient-bluetooth-oximeter-facilitates-patient-monitoring.html) |

Consumer oximeters that work only with their makers' apps, for example
Viatom/Wellue or Contec models, are **excluded**. They use proprietary
protocols.

### Test tools

| Item | Purpose | Indicative price | Source |
|---|---|---|---|
| Nordic nRF52840 USB Dongle (PCA10059) | Emulates a standard BP or SpO2 peripheral from synthetic data, for repeatable tests without a patient | ₹2,025 in India (incl. GST and duty); about US$11–13 abroad | [Tanotis](https://www.tanotis.com/products/sparkfun-nordic-semiconductor-nrf52840-usb-dongle), [SparkFun](https://www.sparkfun.com/nordic-semiconductor-nrf52840-usb-dongle.html) |
| Android test phones (3–4) | Android 9 to 15, including one entry-level phone with 2 GB of RAM. Bluetooth behaviour varies by manufacturer | Estimate only: ₹7,000–15,000 each (not researched per model) | — |

## 3. Proposed purchase, in two steps

**Step 1: bench check.** Approve about **₹15,000–20,000**:
- one A&D UA-651BLE (imported or from a distributor)
- one Nonin 3230 (distributor quote)
- one nRF52840 dongle (about ₹2,025)
- one Omron HEM-7361T (about ₹5,200), only to confirm or rule out the standard profile

**Step 2: validation.** After step 1, and only for models that pass the bench
check:
- 2 more units per passing model
- 3–4 test phones

Estimated at **₹45,000–70,000**. It would be presented for approval with
real quotes.

Everything is excluded from the step 1 figure until it is quoted, including
import duty and shipping for the A&D and Nonin units.

## 4. Before buying (owner checklist)

- [ ] Approve step 1 and its budget
- [ ] Choose the supplier: an Indian distributor preferred, with a GST invoice
- [ ] Confirm the units are new and in date, with a calibration certificate where the maker offers one
- [ ] Confirm the regulatory status in India: imported medical devices need CDSCO registration. Ask the distributor for the import licence
- [ ] Decide where the units are kept and who runs the protocol: a clinician should take part in the readings comparison
