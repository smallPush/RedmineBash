# RedmineBash

Eina de terminal per gestionar tasques de Redmine.
Les ajudes i els missatges són en català; el codi, les ordres, les opcions i les
claus JSON són en anglès. Requereix **Python 3.10 o posterior**, sense paquets
externs, servidor local ni base de dades.

## Primers passos

Des d’aquest directori:

```bash
./tasks check
./tasks
./tasks --help
```

La credencial es llegeix de `TOKEN_REDMINE` a l’entorn i, si no està definida,
de `~/.env`. L’URL es configura de la mateixa manera amb `REDMINE_URL`
(per exemple, `https://redmine.example.com`). Cada variable exportada té
prioritat sobre la del fitxer. El fitxer s’interpreta com a dades, sense executar
shell ni expandir variables. S’admeten assignacions simples, cometes i `export`.

Fes servir `.env.example` com a referència i desa la clau real únicament a
l’entorn o en un fitxer privat. Pots seleccionar un altre fitxer amb
`./tasks --env-file /path/to/private/.env check`. L’URL ha de fer servir HTTPS;
es verifica el certificat i no se segueixen redireccions. Cal tenir accés de
xarxa al servidor i, si escau, a la VPN corporativa.

## Consultar tasques i projectes

```bash
./tasks                            # Les meves tasques obertes, totes les pàgines
./tasks list --project 1443
./tasks list --status "En procés" --priority Normal
./tasks list --status all --assignee all --json
./tasks list --status closed --assignee me
./tasks list --assignee none
./tasks show 107162
./tasks projects
./tasks catalogs --project 1443
```

`list` mostra l’ID, l’estat, la prioritat, el projecte, el títol i el venciment,
ordenats per prioritat i actualització descendents. `--assignee` admet `me`,
`all`, `none` o un ID d’usuari. `--status` admet `open`, `closed`, `all`, un nom
o un ID. Els projectes se seleccionen per ID o identificador de Redmine, que
apareix a `projects`.

`show` inclou la descripció, els camps personalitzats, l’historial, els
comentaris i els estats permesos. `catalogs` consulta les opcions reals:
conserva els noms del servidor, com ara `Tasca` i `En procés`. Per als tipus,
estats i prioritats s’accepten IDs o noms sense distingir majúscules ni accents;
els noms ambigus requereixen un ID. Les consultes admeten `--json`.

## Crear i modificar

**Les ordres següents escriuen a Redmine.** Afegeix `--dry-run` per inspeccionar
el mètode, la ruta i el cos JSON sense enviar l’escriptura. La preparació pot
fer consultes per resoldre IDs i validar les opcions.

```bash
./tasks create --project 1443 --title "Nova tasca" --tracker Tasca --dry-run
./tasks create --project 1443 --title "Nova tasca" --description "Objectiu"
./tasks edit 107162 --description "Descripció actualitzada"
./tasks edit 107162 --priority Normal --due-date 2026-12-01 --progress 25
./tasks edit 107162 --field 15=INT --dry-run
./tasks comment 107162 "Comentari de seguiment"
./tasks status 107162 "En procés"
```

Les tasques noves fan servir el tipus `Tasca`, s’assignen a l’usuari autenticat
i conserven els valors predeterminats de Redmine per a la resta de camps.
Consulta els tipus disponibles a cada projecte i indica `--tracker` quan calgui.
Tant `create` com `edit` admeten `--title`, `--description`, `--tracker`,
`--priority`, `--assignee`, `--due-date`, `--progress` i `--field ID=VALOR`
repetible. En editar, només s’envien els camps sol·licitats.

Fes servir `--assignee none` per eliminar l’assignació, `--due-date ""` per
esborrar la data i `--description ""` per buidar la descripció. El percentatge
és un enter de 0 a 100. Els camps personalitzats s’envien com a text; Redmine
en valida els formats i els camps obligatoris. Pots descobrir-ne els IDs amb
`catalogs --project` i consultar-ne els valors actuals amb `show`.

Redacta els comentaris en català. L’eina conserva el text que introdueixes;
no el tradueix ni el revisa automàticament amb Codex.

`status` només accepta transicions permeses per a la tasca i l’usuari actuals.
Crear, editar, comentar i canviar l’estat són operacions explícites sense
confirmació addicional. No es reintenten escriptures automàticament: si hi ha
un error de connexió, consulta la tasca abans de repetir-les.

## Compatibilitat amb les ordres anteriors

`./tareas` continua disponible com a àlies de `./tasks`. També s’accepten les
ordres i les opcions anteriors en castellà, per exemple
`./tareas listar --proyecto 1443 --estado abiertos --asignado yo`.
Fes servir la interfície anglesa per a les ordres i els scripts nous.

Les claus pròpies de la sortida JSON són ara en anglès: `user`, `statuses`,
`priorities`, `trackers`, `fields` i `result`. Els resultats d’escriptura són
`created` o `updated`. Actualitza els scripts que consumien les claus anteriors.
El contingut retornat per Redmine es conserva en l’idioma original.

## Desenvolupament i validació

```bash
make help
make tasks
make test
# Alternativa sense make:
python3 -m unittest discover -s tests -v
```

Els objectius anteriors `make ayuda` i `make tareas` es mantenen com a àlies.
L’executable `tasks` carrega `redmine_tasks/`: `config.py` llegeix la configuració,
`client.py` implementa HTTP i paginació, i `cli.py` defineix les ordres.
`tests/` conté proves `unittest` amb respostes simulades; no modifica el servidor
ni necessita credencials. No hi ha cap pas de compilació ni dependències que
requereixin un fitxer de bloqueig. Fes servir quatre espais i les convencions
estàndard de Python, amb identificadors, comentaris de codi i docstrings en
anglès. No hi ha cap formatador ni linter configurat.

La sortida normal és llegible; `--json` permet automatitzar consultes i resultats.
Els errors s’escriuen a stderr. Codis de sortida: `0` èxit, `1` error de
configuració o API, `2` arguments no vàlids i `130` interrupció. No s’inclouen
ordres per esborrar tasques ni registrar hores.
