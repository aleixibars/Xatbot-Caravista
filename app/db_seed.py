"""Structured seed data for Caravista Restaurant (Lleida).

Pure data, no DB/SQL here — ``app/db.py`` creates the SQLite schema and loads
these constants into it. Keeping the data as plain Python literals means the
schema-building code has a single, unambiguous source to load from instead of
re-deriving it from prose.

This is the structured half of ADR-0003: facts that must be answered *exactly*
(contact, hours, which menus exist and what they cost, where to book). The
narrative half — the carta's dishes and prices, the wine list, the chef's
career, the takeaway conditions — lives in ``knowledge/caravista.md`` and is
retrieved from Qdrant. A fact that appears in both would let the two halves
disagree inside one answer, so each fact lives on one side only; the menu
prices here are the headline per-person prices, and the dish-by-dish detail
stays in the knowledge base.

Source: caravistarestaurant.com, extracted 2026-09-22. Prices include VAT and
change over time — anything not confirmed by that source is deliberately
absent rather than guessed.

Shapes are load-bearing: ``app/db.py`` unpacks each tuple positionally into
its INSERT statement.
"""

from __future__ import annotations

# Flat company facts — one row per key in SQLite (company_info(key, value)).
# `phone_main`, `whatsapp`, `hours_lunch`, `hours_dinner`, `closed_day` and
# `booking_url` are special: `rag._contact_context()` appends exactly those
# keys to every answer's CONTEXT so the chat model never has to invent a way
# of reaching the restaurant (see `_CONTACT_KEYS` in app/rag.py).
COMPANY_INFO: dict[str, str] = {
    "brand_name": "Caravista Restaurant (Caravista by Mateu Blanch)",
    "sector": (
        "Restaurant-peixateria especialitzat en marisc, peix salvatge, arrossos i fideuàs"
    ),
    "one_liner": (
        "Som Caravista, un restaurant-peixateria de la Zona Alta de Lleida especialitzat "
        "en marisc, peix salvatge, arrossos i fideuàs, amb peixateria pròpia a l'entrada i "
        "verdures de proximitat de l'Horta de Lleida."
    ),
    "address": "Av. de Balmes, 38 (baixos), 25006 Lleida",
    "location": "Lleida (Zona Alta)",
    "maps_url": "https://www.google.com/maps?ll=41.618723,0.619633&z=16",
    "phone_main": "600 764 517",
    "whatsapp": "+34 600 764 517",
    "phone_landline": "973 85 60 09",
    "email": "info@caravistarestaurant.com",
    "website": "https://caravistarestaurant.com",
    "website_ca": "https://caravistarestaurant.com/ca/",
    "booking_url": "https://caravistareservas.com/appointment",
    "hours_lunch": "Dinars: de dimarts a diumenge, de 12:30 a 16:00",
    "hours_dinner": "Sopars: només divendres i dissabte, de 20:00 a 23:00",
    "closed_day": "Dilluns tancat. Tampoc hi ha sopars diumenge nit ni de dimarts a dijous",
    "hours_menu_del_dia": "Menú del dia: només migdies de dimarts a divendres",
    "hours_delivery": (
        "Entrega a domicili: dinars de dimarts a diumenge de 12:45 a 16:00; "
        "sopars divendres i dissabte de 20:00 a 23:00"
    ),
    "hours_takeaway": (
        "Recollida al local: de dimarts a diumenge de 12:30 a 16:00, i divendres i "
        "dissabte de 20:00 a 22:30. Diumenge, consultar disponibilitat"
    ),
    "capacity": "50 comensals en dos menjadors, més barra",
    "private_room": (
        "Un dels menjadors es pot convertir en sala privada per a celebracions i reunions "
        "d'empresa"
    ),
    "table_hold": "La taula es manté 15 minuts a partir de l'hora reservada",
    "delivery_area": (
        "Entrega a domicili només a la ciutat de Lleida; altres poblacions, a consultar"
    ),
    "delivery_notice": (
        "Cal demanar-ho amb 24 hores d'antelació; per a avui mateix, trucar al 600 764 517"
    ),
    "chef": "Mateu Blanch Olaya, xef i copropietari des del març de 2018",
    "owner_legal": "Mateu Blanch Olaya, NIF B25836198",
    "facebook_url": "https://www.facebook.com/CaravistaRestaurant/",
    "instagram_url": "https://www.instagram.com/caravistarestaurant/",
    "tiktok_url": "https://www.tiktok.com/@mateu.chef",
    "twitter_url": "https://twitter.com/Caravistalleida",
    "sister_cafe": (
        "Voravista, cafeteria de cafè d'especialitat dels mateixos socis, al carrer Balmes "
        "36 de Lleida (de dimarts a dissabte de 8:00 a 20:00 i diumenge de 9:00 a 13:30)"
    ),
    "motto": "Tota aventura comença per un sí",
}

# (name, role, department)
TEAM_MEMBERS: list[tuple[str, str, str]] = [
    ("Mateu Blanch Olaya", "Xef i copropietari", "Cuina"),
    ("Hind", "Copropietària de la cafeteria Voravista", "Voravista"),
]

# (area_key, name, one_liner, url)
SERVICES: list[tuple[str, str, str, str]] = [
    (
        "restaurant",
        "Restaurant",
        "Marisc, peix salvatge, arrossos i fideuàs a taula o a la barra, amb peixateria "
        "pròpia a l'entrada.",
        "https://caravistarestaurant.com",
    ),
    (
        "reserves",
        "Reserva de taula",
        "Reserva online, per telèfon o WhatsApp al 600 764 517, o per email; es tria barra "
        "o taula i s'hi poden demanar trona i espai per a cotxet.",
        "https://caravistareservas.com/appointment",
    ),
    (
        "menus",
        "Menús",
        "Menú del dia (23,90 €), infantil (22 €), arrossos (42 €), entrecot (42 €), "
        "mariscada (62 €) i degustació (88 €), a més dels menús de Nadal.",
        "https://caravistarestaurant.com",
    ),
    (
        "grups",
        "Menús de grup i esdeveniments",
        "Quatre menús de grup de 45, 50, 60 i 65 € per persona, i sala privada per a "
        "celebracions i reunions d'empresa.",
        "https://caravistarestaurant.com/wp-content/uploads/MenAos-1-2-3-4-grupos-2024-1.pdf",
    ),
    (
        "emportar",
        "Menjar per emportar i a domicili",
        "Comanda online o per telèfon, amb 24 h d'antelació; entrega només a la ciutat de "
        "Lleida i recollida al local.",
        "https://caravistarestaurant.com/caravista-a-domicilio/",
    ),
    (
        "catering",
        "Càtering per a esdeveniments i empreses",
        "Menús de la carta o personalitzats a casa o a l'empresa: arrossos, tapes, carn i "
        "celler de prop de 50 referències.",
        "https://caravistarestaurant.com/catering-profesional-eventos-empresas/",
    ),
    (
        "xec_regal",
        "Xec regal Experiència Gastronòmica",
        "Xec regal per l'import que es vulgui, bescanviable per qualsevol servei o producte "
        "del restaurant.",
        "https://caravistarestaurant.com/regala-una-experiencia-gastronomica/",
    ),
    (
        "voravista",
        "Voravista (cafeteria germana)",
        "Cafè d'especialitat amb obrador propi i saló privat per a 50 persones, al carrer "
        "Balmes 36 de Lleida.",
        "https://caravistarestaurant.com/noticias/",
    ),
]

# (trigger_examples, area, bot_action)
# `trigger_examples` is one comma-separated string; `db.match_routing_rule`
# splits it and matches each phrase against the question.
ROUTING_RULES: list[tuple[str, str, str]] = [
    (
        "vull reservar taula, reservar una taula, fer una reserva, teniu lloc",
        "Reserves",
        "Ofereix la reserva online a https://caravistareservas.com/appointment o trucar i "
        "escriure per WhatsApp al 600 764 517, i recorda que la taula es manté 15 minuts",
    ),
    (
        "anul·lar la reserva, canviar la reserva, arribaré tard",
        "Reserves",
        "Demana que truquin al 600 764 517 com abans millor; la taula només es guarda 15 "
        "minuts a partir de l'hora reservada",
    ),
    (
        "quin horari feu, a quina hora obriu, obriu avui, obriu els dilluns",
        "Horaris",
        "Dinars de dimarts a diumenge de 12:30 a 16:00 i sopars només divendres i dissabte "
        "de 20:00 a 23:00; dilluns tancat",
    ),
    (
        "som un grup, celebració, aniversari, comunió, dinar d'empresa, sopar d'empresa",
        "Grups i esdeveniments",
        "Explica els menús de grup (45, 50, 60 i 65 €) i la sala privada, i deriva al 600 "
        "764 517 per tancar dia i menú",
    ),
    (
        "menjar per emportar, porteu a domicili, comanda a domicili, delivery",
        "Per emportar i domicili",
        "Explica la comanda online, les 24 hores d'antelació i que només es reparteix a la "
        "ciutat de Lleida; per a avui, trucar al 600 764 517",
    ),
    (
        "voldria un càtering, càtering per a empresa, menjar a casa per a un esdeveniment",
        "Càtering",
        "Explica que es fan menús de la carta o a mida a casa o a l'empresa i deriva al 600 "
        "764 517 o info@caravistarestaurant.com",
    ),
    (
        "sóc al·lèrgic, al·lèrgies, intoleràncies, sense gluten, vegetarià, vegà",
        "Al·lèrgies i intoleràncies",
        "Indica les opcions marcades a la carta i insisteix que ho diguin en reservar i al "
        "personal de sala, que ho confirmarà plat a plat",
    ),
    (
        "vull regalar un dinar, xec regal, targeta regal",
        "Xec regal",
        "Explica el xec regal Experiència Gastronòmica i enllaça la pàgina de regal",
    ),
    (
        "vull la factura, reclamació, la comanda no era correcta, devolució",
        "Comandes online",
        "Demana que escriguin a info@caravistarestaurant.com amb les dades de la comanda",
    ),
    (
        "vull treballar amb vosaltres, busqueu personal, enviar currículum",
        "Feina",
        "Enllaça el formulari de Treballa amb nosaltres i l'email "
        "info@caravistarestaurant.com",
    ),
    (
        "quant costa, preu, pressupost per a un grup",
        "Preus",
        "Dona els preus dels menús que constin a la carta i, per a pressupostos a mida, "
        "deriva al 600 764 517 sense inventar cap import",
    ),
]

# (question, answer)
FAQ: list[tuple[str, str]] = [
    (
        "On sou i com s'hi arriba?",
        "Som a l'Avinguda de Balmes, 38 (baixos), a la Zona Alta de Lleida. Al mapa: "
        "https://www.google.com/maps?ll=41.618723,0.619633&z=16",
    ),
    (
        "Quin horari feu?",
        "Servim dinars de dimarts a diumenge de 12:30 a 16:00, i sopars només divendres i "
        "dissabte de 20:00 a 23:00. Dilluns tanquem.",
    ),
    (
        "Obriu els dilluns?",
        "No, el dilluns és el nostre dia de descans.",
    ),
    (
        "Feu sopars entre setmana?",
        "No. Només fem sopars divendres i dissabte, de 20:00 a 23:00.",
    ),
    (
        "Com puc reservar taula?",
        "Online a https://caravistareservas.com/appointment, per telèfon o WhatsApp al 600 "
        "764 517, o per email a info@caravistarestaurant.com. Pots triar barra o taula i "
        "demanar trona o espai per a cotxet.",
    ),
    (
        "Quant de temps guardeu la taula?",
        "La mantenim 15 minuts a partir de l'hora reservada; després queda lliure per a "
        "altres clients. Si vas tard, truca'ns al 600 764 517.",
    ),
    (
        "Puc reservar per a d'aquí a més de tres mesos?",
        "Sí, però per a dates a més de tres mesos vista és millor reservar per telèfon (600 "
        "764 517) o per email (info@caravistarestaurant.com).",
    ),
    (
        "Teniu menú del dia?",
        "Sí, 23,90 € per persona, només els migdies de dimarts a divendres (festius i dies "
        "temàtics no hi entren). Inclou primer, segon, postre i una copa de vi, cervesa, "
        "aigua o refresc.",
    ),
    (
        "Quins menús teniu i quant valen?",
        "Menú del dia 23,90 €, menú infantil 22 €, menú arrossos 42 €, menú entrecot 42 €, "
        "menú mariscada 62 € i menú degustació 88 € (aquest, a taula completa). També tenim "
        "menús de grup de 45, 50, 60 i 65 €, i menús de Nadal, Sant Esteve i Cap d'Any.",
    ),
    (
        "Quina és l'especialitat de la casa?",
        "El marisc fresc (mariscada, gambes vermelles de Palamós, llamàntol, ostres "
        "Gillardeau), el peix salvatge a la planxa (rap, llobarro, llenguado, turbot), els "
        "arrossos i les fideuàs. Tenim peixateria pròpia a l'entrada.",
    ),
    (
        "Els arrossos són per a una sola persona?",
        "Els arrossos i les fideuàs són per a un mínim de 2 persones i el preu és per "
        "persona. Els pots demanar secs, melosos o caldosos.",
    ),
    (
        "Teniu opcions per a nens?",
        "Sí: menú infantil per 22 € (espaguetis amb tomàquet i parmesà, fingers de pollastre "
        "amb patates i postre). També tenim trona i espai per a cotxet; indica-ho quan "
        "reservis.",
    ),
    (
        "Teniu opcions vegetarianes, veganes o sense gluten?",
        "A la carta hi ha plats com l'amanida verda de l'Horta, el sashimi vegetal de "
        "moniato, la crema de bolets o el risotto de bolets i tòfona, i la carta de postres "
        "marca els sense gluten, vegans i sense lactosa. Per a al·lèrgies i intoleràncies, "
        "digue'ns-ho en reservar i el personal t'ho confirmarà plat a plat.",
    ),
    (
        "Teniu carn?",
        "Sí: entrecot d'Angus de 35 dies, chuletón de vedella frisona, cabrit lechal, "
        "garrinet, secret ibèric i caneló XL de cua de bou.",
    ),
    (
        "Puc celebrar un esdeveniment privat o venir amb un grup?",
        "Sí. Tenim capacitat per a 50 comensals i un dels menjadors es pot convertir en sala "
        "privada. Hi ha menús de grup de 45 a 65 € i menús a mida: truca'ns al 600 764 517. "
        "La cafeteria Voravista (Balmes 36) també té saló privat per a 50 persones.",
    ),
    (
        "Feu menjar per emportar o a domicili?",
        "Sí. Pots demanar-ho online a "
        "https://caravistarestaurant.com/caravista-a-domicilio/ o al 600 764 517. Repartim "
        "només a la ciutat de Lleida (altres poblacions, a consultar) i cal avisar amb 24 "
        "hores; per a avui mateix, truca'ns. Per recollir al local: de dimarts a diumenge de "
        "12:30 a 16:00 i divendres i dissabte de 20:00 a 22:30.",
    ),
    (
        "Feu càtering?",
        "Sí, càtering per a esdeveniments i empreses, amb els menús de la carta o "
        "personalitzats: arrossos, tapes, carn i celler. Consulta'ns al 600 764 517.",
    ),
    (
        "Puc regalar un àpat?",
        "Sí, amb el xec regal Experiència Gastronòmica, per l'import que vulguis: menú del "
        "dia, arrossos, entrecot, mariscada, degustació o menú a mida.",
    ),
    (
        "Com demano la factura d'una comanda online?",
        "Escriu-nos a info@caravistarestaurant.com amb les dades de la comanda.",
    ),
    (
        "Qui és el xef?",
        "Mateu Blanch Olaya, copropietari des del 2018, amb experiència en restaurants amb "
        "estrella Michelin (La Boscana, Malena, Carballeira), Medalla d'Or 2022 i Plat d'Or "
        "2019 de Radio Turismo, i pioner en cuina 3D amb Food Ink.",
    ),
    (
        "Teniu vins de Lleida?",
        "Sí, el celler està centrat en la DO Costers del Segre (Raimat, Castell del Remei, "
        "Tomàs Cusiné, Castell d'Encús, Lagravera, Clos Pons, Analec, Cristiari...), i també "
        "tenim Priorat, Rioja, Ribera del Duero, Rías Baixas, Rueda, cava, Corpinnat i "
        "xampany. Fins i tot un albariño sense alcohol.",
    ),
    (
        "Quin postre és el més típic?",
        "La Torrija lleidatana Ruta Monumental, el Xuxo Xoco-tassa i el postre sorpresa "
        "Trenca't el coco. Les postres valen 9,90 €.",
    ),
    (
        "Es pot aparcar o com s'hi va?",
        "Som a l'Avinguda de Balmes 38, a la Zona Alta de Lleida; aquí tens la ubicació: "
        "https://www.google.com/maps?ll=41.618723,0.619633&z=16",
    ),
]

# (label, url)
LINKS: list[tuple[str, str]] = [
    ("Web", "https://caravistarestaurant.com"),
    ("Web en català", "https://caravistarestaurant.com/ca/"),
    ("Reserva online", "https://caravistareservas.com/appointment"),
    ("Carta", "https://caravistarestaurant.com/wp-content/uploads/Carta_Caravista.pdf"),
    ("Carta de postres", "https://caravistarestaurant.com/wp-content/uploads/Carta_postres.pdf"),
    ("Carta de vins", "https://caravistarestaurant.com/wp-content/uploads/Carta-de-Vi_2026.pdf"),
    (
        "Menús de grup",
        "https://caravistarestaurant.com/wp-content/uploads/MenAos-1-2-3-4-grupos-2024-1.pdf",
    ),
    (
        "Carta de sopars d'empresa",
        "https://caravistarestaurant.com/wp-content/uploads/carta-sopar-empreses.pdf",
    ),
    ("Menjar a domicili", "https://caravistarestaurant.com/caravista-a-domicilio/"),
    (
        "Flyer per emportar",
        "https://caravistarestaurant.com/wp-content/uploads/Flayer_Per-emportar.pdf",
    ),
    ("Xec regal", "https://caravistarestaurant.com/regala-una-experiencia-gastronomica/"),
    ("Càtering", "https://caravistarestaurant.com/catering-profesional-eventos-empresas/"),
    ("Notícies", "https://caravistarestaurant.com/noticias/"),
    ("Treballa amb nosaltres", "https://caravistarestaurant.com/trabaja-con-nosotros/"),
    ("Google Maps", "https://www.google.com/maps?ll=41.618723,0.619633&z=16"),
    ("Facebook", "https://www.facebook.com/CaravistaRestaurant/"),
    ("Instagram", "https://www.instagram.com/caravistarestaurant/"),
    ("TikTok del xef", "https://www.tiktok.com/@mateu.chef"),
    ("Política de privacitat", "https://caravistarestaurant.com/politica-de-privacidad"),
    ("Avís legal", "https://caravistarestaurant.com/aviso-legal"),
    (
        "Condicions generals de venda",
        "https://caravistarestaurant.com/condiciones-generales-de-venta",
    ),
]
