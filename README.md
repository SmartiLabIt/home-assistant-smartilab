# SmartiLab for Home Assistant

Your SmartiLab devices in Home Assistant, through the SmartiLab cloud: switches, lights, sensors,
numbers, choices, texts and buttons, with every change arriving as it happens. It works from
anywhere: Home Assistant and the devices do not need to be on the same network.

*In italiano più sotto.*

## What you need

- A SmartiLab account with your devices in the console (https://smartilab.it/console/).
- Home Assistant 2026.1 or later.
- For a Professional device, a licence in force that gives control from the internet.

## Install

1. In Home Assistant open **HACS**, the three dots, **Custom repositories**.
2. Add `https://github.com/SmartiLabIt/home-assistant-smartilab`, type **Integration**.
3. Find **SmartiLab** in HACS, **Download**, then restart Home Assistant.

## Add your account

1. **Settings → Devices & services → Add integration → SmartiLab**.
2. The sign-in page of smartilab.it opens: sign in, read what Home Assistant asks, press **Allow**.
3. Back in Home Assistant your devices appear, the ones you own and the ones shared with you.

Home Assistant may read your devices and command them, never more than your account can: a device
shared with you to be seen only cannot be commanded. You remove the access from the SmartiLab
console (Settings, Integrations, Access), and it stops at once.

## What you see

| On the device | In Home Assistant |
|---|---|
| A switch, a socket, a relay | switch |
| A light | light, with brightness and colour when the device has them |
| A value: temperature, humidity, battery, level… | sensor, with its unit |
| Something true or false: a catch, a problem, motion | binary sensor |
| A number you set | number |
| One of fixed values | select |
| A text you set | text |
| A simple command | button |
| A part of a device, such as a trap of a hub | a device of its own, under the hub |

A device that is not connected shows its entities as unavailable. Values arrive on the live channel
of the SmartiLab cloud as they change; if the channel drops, the integration reads the state every
minute until it is back.

**Local and cloud.** LoopMaxPro boards can also show themselves to Home Assistant on the network of
the house, through an MQTT broker. If you use that too, the same device appears twice: keep one.

## Support

Problems and ideas: https://github.com/SmartiLabIt/home-assistant-smartilab/issues

## For who develops

Against a development console, in `configuration.yaml`:

```yaml
smartilab:
  server: http://host.docker.internal:8180   # how Home Assistant reaches the console
  browser: http://localhost:8180             # how the browser opens it, for the sign-in page
```

The tests of the part that needs no Home Assistant: `python3 -m unittest discover -s tests`.

---

## In italiano

I tuoi dispositivi SmartiLab in Home Assistant, attraverso il cloud SmartiLab: interruttori, luci,
sensori, numeri, scelte, testi e tasti, con ogni cambio che arriva subito. Funziona da ovunque:
Home Assistant e i dispositivi non devono stare nella stessa rete.

**Installare.** In HACS, i tre puntini, **Custom repositories**: aggiungi
`https://github.com/SmartiLabIt/home-assistant-smartilab`, tipo **Integration**; poi **SmartiLab**,
**Download**, e riavvia Home Assistant.

**Aggiungere l'account.** **Impostazioni → Dispositivi e servizi → Aggiungi integrazione →
SmartiLab**: si apre la pagina di accesso di smartilab.it, entri e premi **Consenti**. Tornato in
Home Assistant compaiono i tuoi dispositivi, i tuoi e quelli condivisi con te.

Home Assistant può leggere e comandare i tuoi dispositivi, mai più di quello che può il tuo account.
L'accesso lo togli dalla console SmartiLab (Impostazioni, Integrazioni, Accessi), e smette subito.

Per un dispositivo Professional serve una licenza in vigore che dia il controllo da internet. Se usi
anche il collegamento di casa delle schede LoopMaxPro (MQTT), lo stesso dispositivo compare due
volte: tienine uno.
