"""A small made-up family that shows off the tricky cases:

* Ruth Hayes (née Miller): a maiden name.
* Samuel was born Samuel Doyle. When his parents died he was adopted by
  George and Linda Hayes, so he is legally Emma's brother and, by blood,
  her second cousin.
* Emma married twice (once ending in divorce); her second husband Dan is
  stepfather to her daughter Lucy.
"""


def load_sample(store):
    P = {}

    def person(key, given, surname, sex, born="", born_at="", died="", died_at="",
               notes="", alt=()):
        P[key] = store.save_person({
            "given_names": given, "birth_surname": surname, "sex": sex,
            "birth_date": born, "birth_place": born_at, "death_date": died,
            "death_place": died_at, "notes": notes,
            "alt_names": [{"kind": k, "surname": s, "from_date": d} for k, s, d in alt],
        })

    def couple(a, b, kind="marriage", start="", place="", end="", reason=""):
        store.save_couple({"partner1_id": P[a], "partner2_id": P[b], "kind": kind,
                           "start_date": start, "start_place": place,
                           "end_date": end, "end_reason": reason})

    def child(c, *parents, kind="biological", date=""):
        for p in parents:
            store.add_parent_link(P[c], P[p], kind, date)

    person("walter", "Walter James", "Hayes", "M", "12 Mar 1890", "Dayton, Ohio",
           "1961", "Dayton, Ohio", "Ran the hardware store on Fifth Street for forty years.")
    person("ruth", "Ruth Ann", "Miller", "F", "1893", "Springfield, Ohio", "1975", "Dayton, Ohio",
           alt=[("married", "Hayes", "1914")])
    couple("walter", "ruth", start="6 Jun 1914", place="Springfield, Ohio",
           end="1961", reason="death")

    person("arthur", "Arthur", "Hayes", "M", "1915", "Dayton, Ohio", "1990")
    person("edith", "Edith", "Clarke", "F", "1917", died="1999", alt=[("married", "Hayes", "1940")])
    person("margaret", "Margaret", "Hayes", "F", "1918", "Dayton, Ohio", "2001",
           alt=[("married", "Doyle", "1943")])
    person("frank", "Francis", "Doyle", "M", "1916", died="1988")
    child("arthur", "walter", "ruth")
    child("margaret", "walter", "ruth")
    couple("arthur", "edith", start="1940")
    couple("margaret", "frank", start="1943")

    person("george", "George", "Hayes", "M", "1942", "Columbus, Ohio")
    person("linda", "Linda", "Park", "F", "1944", alt=[("married", "Hayes", "1967")])
    person("peter", "Peter", "Doyle", "M", "1945", died="1980", died_at="Toledo, Ohio")
    person("carol", "Carol", "Wynn", "F", "1947", died="1980", died_at="Toledo, Ohio",
           alt=[("married", "Doyle", "1972")])
    child("george", "arthur", "edith")
    child("peter", "margaret", "frank")
    couple("george", "linda", start="1967")
    couple("peter", "carol", start="1972", end="1980", reason="death")

    person("emma", "Emma", "Hayes", "F", "1970", "Columbus, Ohio",
           alt=[("married", "Reyes", "1995"), ("married", "Okafor", "2006")])
    person("samuel", "Samuel", "Doyle", "M", "1975", "Toledo, Ohio",
           notes="Born Samuel Doyle. Adopted by his father's cousin George after the 1980 accident.",
           alt=[("adopted", "Hayes", "1981")])
    child("emma", "george", "linda")
    child("samuel", "peter", "carol")
    child("samuel", "george", "linda", kind="adoptive", date="1981")

    person("tom", "Tom", "Reyes", "M", "1968")
    person("dan", "Daniel", "Okafor", "M", "1969")
    person("lucy", "Lucy", "Reyes", "F", "1998")
    couple("emma", "tom", start="1995", end="2003", reason="divorce")
    couple("emma", "dan", start="2006")
    child("lucy", "emma", "tom")
    child("lucy", "dan", kind="step", date="2006")

    store.save_story({
        "title": "The winter of 1980",
        "date": "1980",
        "told_by": "Linda Hayes",
        "body": ("After the accident on the Toledo road, George drove up that same night. "
                 "Sam was five and had never met us, but he fell asleep on George's shoulder "
                 "before we were out of the city. The adoption was final the next spring."),
        "person_ids": [P["samuel"], P["george"], P["linda"], P["peter"], P["carol"]],
    })
    store.set_meta("family_name", "The Hayes Family")
    return P
