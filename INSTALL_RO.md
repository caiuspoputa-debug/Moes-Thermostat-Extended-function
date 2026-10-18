# Instalare Moes Relay Heating v0.0.2

## Ce face

Termostatul `climate` este sursa de informație. Ieșirea integrării rămâne
binary sensorul existent **Cerere căldură**. Numele integrării **Moes Relay
Heating** și domeniul `moes_relay_heating` sunt păstrate pentru compatibilitate.

Versiunea 0.0.2 elimină câmpul releu și toate comenzile directe către relee.
Un câmp releu salvat de versiunea veche este ignorat; nu este obligatoriu și
nu împiedică încărcarea zonei. Integrarea nu pornește și nu oprește niciun
releu, inclusiv la pornire, oprire sau lipsa datelor termostatului.

## Instalarea sau actualizarea componentei

Pachetul păstrează structura pentru HACS, inclusiv `hacs.json`. Pentru o
instalare HACS existentă, actualizează componenta din repository-ul deja
configurat când versiunea 0.0.2 este disponibilă și repornește Home Assistant.

Pentru actualizare manuală:

1. Păstrează o copie a componentei instalate.
2. Copiază folderul `custom_components/moes_relay_heating` din pachet peste
   `/config/custom_components/moes_relay_heating` din Home Assistant.
   Nu crea un folder `custom_components` suplimentar în interiorul componentei.
3. Repornește Home Assistant.
4. Verifică versiunea `0.0.2` în manifestul instalat și încărcarea fără erori.

Păstrează intrările existente ale integrării și numele zonelor. Actualizarea
nu cere ștergerea sau recrearea intrărilor, redenumirea entităților ori
schimbarea ID-urilor. Nu este impus un `entity_id` nou. Entitatea existentă,
identificatorul dispozitivului și istoricul ei rămân asociate aceleiași identități.

Integrarea este livrată separat; pachetul nu conține și nu instalează
automatizări. Controlul releelor este în afara acestei integrări.

## Setările zonei

Sunt disponibile numai:

1. `zone_name` — numele zonei;
2. `thermostat` — termostatul ales din lista entităților `climate`;
3. `hysteresis` — histerezisul de pornire, implicit `1.0°C`.

Releul nu mai apare în configurare sau opțiuni. Datele vechi pentru releu
nu sunt folosite, fără să fie necesară recrearea configurației.

## Logica cererii de căldură

Cu termostatul în `heat` și:

```text
TARGET = 23°C
HISTEREZIS = 1°C
```

logica este:

```text
CURRENT <= 22°C -> Cerere căldură ON
CURRENT >= 23°C -> Cerere căldură OFF
22°C < CURRENT < 23°C -> păstrează cererea anterioară
```

Regula generală rămâne: ON la `current <= target - hysteresis`, OFF la
`current >= target`, iar între praguri se păstrează valoarea precedentă.
Ultima cerere este păstrată și la restart pentru continuarea histerezisului.

În alt mod HVAC decât `heat`, cererea este OFF. Dacă termostatul lipsește,
este `unknown`/`unavailable` sau nu are temperatura curentă/țintă, cererea este
tot OFF. Acestea sunt decizii ale binary sensorului, nu o comandă sau o oprire
de siguranță aplicată unui releu.

## Icon

Iconul este inclus exact în:

```text
custom_components/moes_relay_heating/brand/icon.png
custom_components/moes_relay_heating/brand/icon@2x.png
```

## Revenire și validare

Pentru revenire, restaurează copia componentei precedente și repornește
Home Assistant. Nu șterge intrarea existentă și nu redenumi entitățile.

Au trecut toate cele 16 teste locale, fără erori sau teste sărite. Au fost
verificate identitatea entității, histerezisul, configurația veche și lipsa
accesului/comenzilor către relee. Vezi TEST_REPORT.json și TEST_LOG.txt.
Pachetul nu a fost instalat pe Home Assistant și nu a fost verificat pe
echipamentele reale de încălzire în această sesiune.
