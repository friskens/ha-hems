# Installation och första kontroll

HEMS Client är en fristående klient till HEMS från [PowerGravio](https://powergravio.se). Version 0.1.0a3 är en alfa: mätinsamling och beslutsvisning finns, medan batteristyrning kräver egna HA-skript enligt [adapterkontraktet](ADAPTER.md). Någon färdig Fronius-drivrutin eller automatisk styrning av bil/avfuktare ingår ännu inte.

1. Lägg till `https://github.com/friskens/ha-hems` som anpassat integrationsrepo i HACS. Visa förhandsversioner om det behövs.
2. Installera, starta om HA och lägg till **HEMS Client**.
3. Ange leverantörens fullständiga HTTPS-adress och API-nyckel. Nyckeln skickas endast i `X-Api-Key`.
4. Välj batteriets SOC, nätets effekt, batteriets effekt och en eller flera solproduktionssensorer. Nätimport och batteriladdning ska vara positiva; tecknen kan vändas i inställningarna.
5. Låt styrbrytaren vara av medan mätningar och beslut kontrolleras. Ange därefter skript för kommando och återgång till Auto samt vilka kommandon adaptern faktiskt stöder.

Solproduktionen ska inkludera direkt laddning av batteriet. Summera inte en totalsensor med dess delmätningar. Bilens SOC kan skickas även om laddaren inte styrs.

Integrationen skriver aldrig SOC-gränser. Behåll batteritillverkarens och din installationens inställningar lokalt. Styrningen ändrar inte befintliga YAML-automationer; vid en framtida migrering måste gamla skrivare stängas av så att bara en styr batteriet.

Styrbrytaren visar önskad drift. Vid tillfälliga fel försöker klienten återgå till Auto och återupptar sedan driften efter verifierad återhämtning. Den ska inte bli permanent avstängd av ett kommunikationsfel. Ett manuellt stopp gäller tills du själv slår på igen.

Installation via HACS och konfigurering av 0.1.0a3 har kontrollerats i HA 2026.9.3, med testposten lämnad inaktiverad. Se [riktiga konfigurationsbilder](SCREENSHOTS.md). Automatiska tester körs med simulerade HA-tjänster; molnkommunikation och hårdvarustyrning är ännu inte verifierade i skarp drift med den paketerade integrationen. Ursprungliga installationens erfarenheter finns i [Lessons learned](LESSONS_LEARNED.md).

Gränssnittet finns på svenska och engelska och följer språkvalet i Home Assistant. Det omfattar inställningar, entitetsnamn, driftlägen, status och felmeddelanden.

Observera: HEMS kontrollerar inte åldern på bilens laddnivå. Källintegrationen ansvarar för aktuella värden och ska markera oanvändbara värden som otillgängliga. Ingen timeout eller tidssensor för bilens SOC konfigureras här.
