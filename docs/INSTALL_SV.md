# Installation och migration till 0.2

HEMS Client samlar in valda Home Assistant-mätvärden, skickar dem till HEMS och
visar HEMS beslut som entiteter. Den styr inte växelriktare, laddare eller andra
laster. Din egen automation eller template utför den lokala styrningen.

## Installera

1. Lägg till `https://github.com/friskens/ha-hems` som anpassat
   integrationsrepo i HACS och visa förhandsversioner.
2. Installera en publicerad HEMS Client-release och starta om Home Assistant.
3. Lägg till **HEMS Client** under Inställningar → Enheter och tjänster.
4. Ange HEMS HTTPS-basadress eller fullständig endpoint och API-nyckel. En
   basadress får automatiskt `/battery`; en uttrycklig sökväg behålls.
5. Välj de befintliga sensorer som klienten frågar efter. Fixa eventuella
   Repairs för saknad eller inkompatibel sensor.
6. Bygg en lokal automation som triggar när `sensor.hems_decision` ändras.
   Lägg till villkor för färskt beslut, en `choose`-gren per action och
   `mode: restart` så att ett nytt beslut avbryter en tidigare sekvens.

## Viktigt vid uppgradering från 0.1

> **Brytande ändring:** 0.2.0a1 kör inga adapter-skript och gör inga HA-serviceanrop
> för att styra utrustning. Bygg och testa din automation innan uppgraderingen
> om du tidigare använde HEMS Clients adapterstyrning.

Beslutssensorn visar fortfarande bland annat `action`, `power_kw`, `power_w`,
`command_interval_seconds`, `loads` och om beslutet är färskt. För
`selfconsumption` betyder `power_kw` maximalt tillåten urladdning; noll blockerar
urladdning. Betydelsen för varje action finns i [PROTOCOL.md](PROTOCOL.md).

Laster och billaddare är endast information. Matcha en laddare på dess stabila
HEMS-`uid`, eller en annan last på `id`. Ett namn från HEMS är endast ett
visningsnamn och kan ändras utan att entiteten byts. En tillfälligt frånvarande
utgång raderas inte automatiskt.

## Mätvärden och färskhet

Nätimport är positiv och batteriladdning positiv. Välj icke-överlappande
solproduktionssensorer och inkludera PV som laddar batteriet direkt. Tre
fasströmmar måste väljas tillsammans från nätmätaren vid anslutningspunkten,
inte växelriktarens egna fasströmmar.

Ett långsamt källsystem stoppar inte utbytet direkt. Klienten skickar senast
giltiga värde och markerar fältet som `stale` efter kontraktets tidsgräns.
Saknade värden uppfinns aldrig som noll. Ett Repair gäller felaktigt eller
saknat sensorval, inte en vanlig tillfällig försening.

## Följsamhet

HEMS följsamhet är en mjuk informationssignal: följer, följer inte, väntar eller
kan inte avgöra. Den använder lokala mätningar efter ett nytt beslut men skriver
aldrig, försöker aldrig igen och skickas inte tillbaka till HEMS. När en action
är ny väntar den först; ett färskt HEMS-svar och en separat lokal observation
krävs innan den kan säga något säkert.
