# Heirloom

A family tree keeper that runs on your own computer. Record people, marriages,
maiden names, births and deaths, family stories and photos, and see it all as
a tree you can explore. Nothing is uploaded anywhere: your family's history
stays in a folder you control.

Heirloom is built to handle real families, not just tidy ones:

- **Adoption, step, foster, guardianship, donors and surrogates** are all
  first-class. A person can have birth parents and adoptive parents at the
  same time, and the tree draws each kind of line differently.
- **Adopted within the family.** If a child was born a second cousin and later
  adopted by their cousin's parents, Heirloom knows both facts. Ask "How are
  we related?" and it answers: *through adoption, Samuel is Emma's brother;
  by blood, Samuel is Emma's second cousin.*
- **Several marriages**, with how each ended (divorce, death, annulment,
  separation), and partnerships that weren't marriages.
- **Names that change.** The name someone was born with is kept, so maiden
  names are never lost. Married, adopted and changed names are recorded with
  the date they began.
- **Cousin marriages and other loops** (one ancestor reached by two lines)
  are drawn once and named correctly, for example as "father" and also
  "first cousin once removed".

## Starting it

You need **Python 3.8 or newer**. Nothing else to install.
Get Python free from <https://www.python.org/downloads/> (on Windows, tick
"Add python.exe to PATH" during install).

- **Windows:** double-click `Start Heirloom (Windows).bat`
- **Mac:** double-click `Start Heirloom (Mac).command`. The first time, macOS
  may refuse; right-click it, choose **Open**, then **Open** again.
- **Any system:** `python3 start_heirloom.py`

Your browser opens to Heirloom. Leave the small black window open while you
work; close it (or press Ctrl+C) when you're done. Everything is saved as you go.

New to it? On the empty screen, click **See an example family** to explore a
sample tree with an adoption, a divorce and a stepfather, then try
**How are we related?** with Emma and Samuel. Start a fresh folder (below) for
your real family.

## Where your family's data lives

In a folder called `family-data` next to the program:

- `family.db` holds every person, relationship and story (a standard SQLite file)
- `photos/` holds your photos, kept exactly as you uploaded them

To keep a different family separately, or keep your data somewhere else
(such as a synced Dropbox or OneDrive folder), start it with:

```
python3 start_heirloom.py --data "/path/to/Smith Family"
```

### Keeping it safe

Use **Import & save → Download a full backup**. You get one zip with the
database, every photo, and a GEDCOM copy that any genealogy program can open.
Keep a copy somewhere other than your computer. To restore, unzip it and start
Heirloom with `--data` pointing at the unzipped folder.

## Moving data in and out

**Import & save → Import a GEDCOM file** reads the standard file that Ancestry,
FamilySearch, MyHeritage and most genealogy programs export (on Ancestry: Trees
→ Tree Settings → Export tree). Adoption and foster details are read from all
the places programs store them. Photos aren't included in GEDCOM files, so add
those separately.

**Export as GEDCOM** writes your tree back out in the same format, including
adoption and step relationships and your stories.

## Using it

- **Tree:** click a person for their details; double-click to centre the tree
  on them. Drag to move around and scroll (or pinch) to zoom. Choose how many
  generations up and down to show.
- **Adding relatives:** open a person and use **Add parent**, **Add partner** or
  **Add child**. Choose *Someone new* or *Someone already in the tree*. The
  second option is how you record that a cousin was later adopted by an aunt.
  Pick the kind of parent (birth, adoptive, step, foster…). The ✎ beside any
  relative lets you change or remove that link.
- **Dates** can be written however you know them: `5 Mar 1923`, `abt 1900`,
  `1890s`, `bef 1850`.
- **Stories** can involve several people and record who told them.
- **Photos** can be tagged with everyone in them, and any photo can become a
  person's portrait on the tree.

## How relationships are worked out

Heirloom looks at the family two ways:

- **By blood:** only birth (and donor) links.
- **Legally:** adoptive links, plus birth links that an adoption didn't
  replace. A full adoption replaces both birth parents. A step-parent adoption
  replaces only the parent who isn't married to the adopter.

When the two answers differ, it shows both. Step, foster, spouse and in-law
relationships come from marriages and the other link kinds.

## For developers

Pure Python standard library on the back end and plain JavaScript on the
front end: no dependencies and no build step, so it should keep running for
a very long time.

```
heirloom/db.py        storage (SQLite) and the data model
heirloom/kinship.py   relationship calculator
heirloom/gedcom.py    GEDCOM import/export
heirloom/server.py    local web server and JSON API (listens on 127.0.0.1 only)
heirloom/static/      the interface
tests/                python3 -m unittest
```

## License

MIT. Free for anyone to use, change and share; see `LICENSE`.
