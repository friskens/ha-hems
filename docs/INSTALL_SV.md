# Installation och första kontroll

Aktuell utvecklingsversion skickar giltiga mätvärden var 20:e sekund, oberoende
av svarets `command_interval_seconds`. Den läser HA:s befintliga tillstånd och
ökar inte avläsningen av växelriktarregister. Kommandon som adaptern inte stöder
visas med `command_supported: false` och felet `unsupported_adapter_command`.
Klienten skickar ingen lokal Auto-återställning. Detta kvitteras ännu inte till
molntjänsten.

Kontrollera solsensorerna nattetid: färska 0 W fungerar, men `unavailable` är
inte samma sak som null. Saknade frivilliga värden stoppar inte urladdningen.
`selfconsumption` och `power_kw` skickas till den lokala adaptern som kommando
och maximalt urladdningstak, oberoende av EV-laddning. Noll betyder noll
tillåten urladdning; en saknad gräns avvisas. Val av växelriktarläge och
lokala optimeringar hör hemma i adapter-skripten. Den lokala adaptern måste
stödja de angivna kommandona innan denna version aktiveras.

HEMS Client är en fristående klient till HEMS från [PowerGravio](https://powergravio.se). Version 0.1.0a7 är en alfa: mätinsamling och beslutsvisning finns, medan batteristyrning kräver egna HA-skript enligt [adapterkontraktet](ADAPTER.md).

1. Lägg till `https://github.com/friskens/ha-hems` som anpassat integrationsrepo i HACS. Visa förhandsversioner om det behövs.
2. Installera, starta om HA och lägg till **HEMS Client**.
3. Ange leverantörens fullständiga HTTPS-adress och API-nyckel. Nyckeln skickas endast i `X-Api-Key`.
4. Välj sensorer för batteriets SOC, nätets effekt, batteriets effekt och en eller flera solproduktionssensorer. Nätimport och batteriladdning ska vara positiva; tecknen kan vändas i inställningarna.
5. Låt styrskriptet vara av medan mätningar och beslut kontrolleras. Ange därefter ett skript för kommando och verifiering samt vilka kommandon just din lokala adapter faktiskt stödjer. HEMS Client innehåller ingen Fronius-, Modbus- eller annan växelriktardrivrutin.

Solproduktionen ska inkludera direkt laddning av batteriet. Dvs AC effekt på Växelriktaren är inte intressant utan t.ex PV Effekt eller MPPT effekt. Bilens SOC kan skickas även om laddaren inte styrs. För eventuella växelriktare med enbart PV och inget batteri kan såklart AC effekt användas.

Integrationen ändrar aldrig SOC-gränser. Behåll batteritillverkarens och din installationens inställningar lokalt. Styrningen ändrar inte befintliga YAML-automationer det här måste du programmera själv i yaml. (Eller låta en AI skriva ihop några script åt dig)

Kontrollsensorn visar önskad drift. Vid tillfälliga fel visar klienten adapter- eller verifieringsfelet men ändrar inte hårdvarans läge. Lokal adapterpolicy äger eventuell retry eller återgång till Auto. Ett manuellt stopp gäller tills du själv slår på igen.

Installation via HACS och konfigurering av 0.1.0a3 har kontrollerats i HA 2026.9.3, med testposten lämnad inaktiverad. Se [riktiga konfigurationsbilder](SCREENSHOTS.md). Automatiska tester körs med simulerade HA-tjänster. Ursprungliga installationens erfarenheter finns i [Lessons learned](LESSONS_LEARNED.md).

Gränssnittet finns på svenska och engelska och följer språkvalet i Home Assistant. Det omfattar inställningar, entitetsnamn, driftlägen, status och felmeddelanden.

Observera: HEMS kontrollerar inte åldern på bilens laddnivå. Källintegrationen ansvarar för aktuella värden och ska markera oanvändbara värden som otillgängliga. Ingen timeout eller tidssensor för bilens SOC konfigureras här.
