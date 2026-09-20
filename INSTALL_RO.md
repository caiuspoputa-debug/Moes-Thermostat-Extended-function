# Instalare Moes Relay Heating v0.0.1

## Ce face

Termostatul este sursa de informație, iar releul este ieșirea de comandă.

Cu:

```text
TARGET = 23°C
HISTEREZIS = 1°C
```

logica este:

```text
CURRENT <= 22°C -> releu ON
CURRENT >= 23°C -> releu OFF
22°C < CURRENT < 23°C -> păstrează starea existentă
```

Dacă termostatul nu este în `heat`, releul este OFF.

## Configurare

În UI alegi:

1. numele zonei;
2. termostatul din lista entităților `climate`;
3. releul din lista entităților `switch`;
4. histerezisul.

Nu trebuie scris manual niciun `entity_id`.

## Siguranță

Dacă termostatul sau temperaturile devin indisponibile, releul este oprit.

## Icon

Iconul este inclus exact în:

```text
custom_components/moes_relay_heating/brand/icon.png
custom_components/moes_relay_heating/brand/icon@2x.png
```
