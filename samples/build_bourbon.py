"""Builds samples/bourbon-succession.ged: the Legitimist line of succession to
the French throne, from Louis XIV to Louis Alphonse de Bourbon (b. 1974).

    python3 samples/build_bourbon.py

It shows the parts of Heirloom that ordinary families also need: second
marriages (Philip V), a divorce and an annulment, cousin marriages (Isabella
II and Francisco de Asis; Madame Royale and the Duke of Angouleme), a claim
passing sideways to an uncle and then to a distant cousin, and stories.
No adoptions appear in this real line, so none are invented.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from heirloom.db import Store  # noqa: E402
from heirloom.gedcom import export_gedcom  # noqa: E402

FR, SP = "King of France and Navarre", "King of Spain"
LEG = "Legitimist claimant to the French throne"


def build(store):
    P = {}

    def person(key, given, sex, born="", born_at="", died="", died_at="",
               surname="", titles=(), notes=""):
        P[key] = store.save_person({
            "given_names": given, "birth_surname": surname, "sex": sex,
            "birth_date": born, "birth_place": born_at, "death_date": died,
            "death_place": died_at, "notes": notes,
            "facts": [{"kind": "title", "detail": t} for t in titles],
        })

    def marry(a, b, date="", place="", end="", reason="", notes=""):
        store.save_couple({"partner1_id": P[a], "partner2_id": P[b], "kind": "marriage",
                           "start_date": date, "start_place": place,
                           "end_date": end, "end_reason": reason, "notes": notes})

    def child(c, *parents):
        for p in parents:
            store.add_parent_link(P[c], P[p], "biological")

    # ---- France: Louis XIV to the extinction of the senior line (1883)
    person("louis14", "Louis XIV", "M", "5 Sep 1638", "Saint-Germain-en-Laye, France",
           "1 Sep 1715", "Versailles, France", titles=[f"{FR} (1643–1715)"],
           notes="The Sun King. Common ancestor of the French and Spanish Bourbons.")
    person("mt_spain", "Maria Theresa of Spain", "F", "10 Sep 1638", "El Escorial, Spain",
           "30 Jul 1683", "Versailles, France", titles=["Queen of France"])
    marry("louis14", "mt_spain", "9 Jun 1660", "Saint-Jean-de-Luz, France", "1683", "death")

    person("dauphin1", "Louis, Grand Dauphin", "M", "1 Nov 1661", "Fontainebleau, France",
           "14 Apr 1711", "Meudon, France", titles=["Dauphin of France"],
           notes="Heir to Louis XIV, but died four years before him.")
    child("dauphin1", "louis14", "mt_spain")
    person("mav_bavaria", "Maria Anna Victoria of Bavaria", "F", "28 Nov 1660", "Munich, Bavaria",
           "20 Apr 1690", "Versailles, France", titles=["Dauphine of France"])
    marry("dauphin1", "mav_bavaria", "7 Mar 1680", "Châlons, France", "1690", "death")

    person("burgundy", "Louis, Duke of Burgundy", "M", "16 Aug 1682", "Versailles, France",
           "18 Feb 1712", "Marly, France", titles=["Dauphin of France (1711–1712)"])
    person("philip5", "Philip V", "M", "19 Dec 1683", "Versailles, France",
           "9 Jul 1746", "Madrid, Spain",
           titles=[f"{SP} (1700–1724, 1724–1746)", "Duke of Anjou (at birth)"],
           notes=("Born a French prince, Philip became King of Spain in 1700. To end the War of the "
                  "Spanish Succession he renounced his French rights in 1713 (Treaty of Utrecht). "
                  "Legitimists hold that French royal law did not allow that renunciation."))
    child("burgundy", "dauphin1", "mav_bavaria")
    child("philip5", "dauphin1", "mav_bavaria")
    person("ma_savoy", "Marie Adélaïde of Savoy", "F", "6 Dec 1685", "Turin, Savoy",
           "12 Feb 1712", "Versailles, France", titles=["Dauphine of France"])
    marry("burgundy", "ma_savoy", "7 Dec 1697", "Versailles, France", "1712", "death")

    person("louis15", "Louis XV", "M", "15 Feb 1710", "Versailles, France",
           "10 May 1774", "Versailles, France", titles=[f"{FR} (1715–1774)"])
    child("louis15", "burgundy", "ma_savoy")
    person("leszczynska", "Marie Leszczyńska", "F", "23 Jun 1703", "Trzebnica, Silesia",
           "24 Jun 1768", "Versailles, France", titles=["Queen of France"])
    marry("louis15", "leszczynska", "5 Sep 1725", "Fontainebleau, France", "1768", "death")

    person("dauphin2", "Louis, Dauphin of France", "M", "4 Sep 1729", "Versailles, France",
           "20 Dec 1765", "Fontainebleau, France", titles=["Dauphin of France"])
    child("dauphin2", "louis15", "leszczynska")
    person("mj_saxony", "Maria Josepha of Saxony", "F", "4 Nov 1731", "Dresden, Saxony",
           "13 Mar 1767", "Versailles, France", titles=["Dauphine of France"])
    marry("dauphin2", "mj_saxony", "9 Feb 1747", "Versailles, France", "1765", "death")

    person("louis16", "Louis XVI", "M", "23 Aug 1754", "Versailles, France",
           "21 Jan 1793", "Paris, France", titles=[f"{FR} (1774–1792)"],
           notes="Deposed in 1792 and executed during the Revolution.")
    person("louis18", "Louis XVIII", "M", "17 Nov 1755", "Versailles, France",
           "16 Sep 1824", "Paris, France", titles=[f"{FR} (1814–1824)"],
           notes="Restored to the throne after Napoleon. No children.")
    person("charles10", "Charles X", "M", "9 Oct 1757", "Versailles, France",
           "6 Nov 1836", "Gorizia, Austria", titles=[f"{FR} (1824–1830)"],
           notes="Abdicated in the 1830 July Revolution; the Orléans branch took the throne.")
    for k in ("louis16", "louis18", "charles10"):
        child(k, "dauphin2", "mj_saxony")
    person("antoinette", "Marie Antoinette", "F", "2 Nov 1755", "Vienna, Austria",
           "16 Oct 1793", "Paris, France", titles=["Queen of France"])
    marry("louis16", "antoinette", "16 May 1770", "Versailles, France", "1793", "death")

    person("royale", "Marie-Thérèse, Madame Royale", "F", "19 Dec 1778", "Versailles, France",
           "19 Oct 1851", "Frohsdorf, Austria", titles=["Duchess of Angoulême"],
           notes="The only child of Louis XVI and Marie Antoinette to survive the Revolution.")
    child("royale", "louis16", "antoinette")
    person("angouleme", "Louis Antoine, Duke of Angoulême", "M", "6 Aug 1775", "Versailles, France",
           "3 Jun 1844", "Gorizia, Austria", titles=["Dauphin of France (1824–1830)"])
    person("berry", "Charles Ferdinand, Duke of Berry", "M", "24 Jan 1778", "Versailles, France",
           "14 Feb 1820", "Paris, France", notes="Assassinated at the Paris Opéra.")
    child("angouleme", "charles10")
    child("berry", "charles10")
    marry("angouleme", "royale", "10 Jun 1799", "Mitau, Courland",
          notes="First cousins: his father Charles X and her father Louis XVI were brothers. No children.")
    person("mc_sicily", "Maria Carolina of Bourbon-Two Sicilies", "F", "5 Nov 1798", "Caserta, Naples",
           "16 Apr 1870", "Brunnsee, Austria", titles=["Duchess of Berry"])
    marry("berry", "mc_sicily", "17 Jun 1816", "Paris, France", "1820", "death")

    person("chambord", "Henri, Count of Chambord", "M", "29 Sep 1820", "Paris, France",
           "24 Aug 1883", "Frohsdorf, Austria", titles=[f"{LEG} as Henri V (1844–1883)"],
           notes=("Born after his father's murder, he was called 'the miracle child'. He came close to "
                  "restoration in 1873 but refused to accept the tricolour flag. His death without "
                  "children ended the senior line descended from Louis XV."))
    child("chambord", "berry", "mc_sicily")

    # ---- Spain: Philip V's descendants
    person("ml_savoy", "Maria Luisa of Savoy", "F", "17 Sep 1688", "Turin, Savoy",
           "14 Feb 1714", "Madrid, Spain", titles=["Queen of Spain"])
    person("farnese", "Elisabeth Farnese", "F", "25 Oct 1692", "Parma",
           "11 Jul 1766", "Aranjuez, Spain", titles=["Queen of Spain"])
    marry("philip5", "ml_savoy", "1701", "Figueres, Spain", "1714", "death")
    marry("philip5", "farnese", "24 Dec 1714", "Guadalajara, Spain", "1746", "death")

    person("charles3", "Charles III", "M", "20 Jan 1716", "Madrid, Spain",
           "14 Dec 1788", "Madrid, Spain", titles=[f"{SP} (1759–1788)", "King of Naples and Sicily (1734–1759)"])
    child("charles3", "philip5", "farnese")
    person("ma_saxony", "Maria Amalia of Saxony", "F", "24 Nov 1724", "Dresden, Saxony",
           "27 Sep 1760", "Madrid, Spain", titles=["Queen of Spain"])
    marry("charles3", "ma_saxony", "1738", "", "1760", "death")

    person("charles4", "Charles IV", "M", "11 Nov 1748", "Portici, Naples",
           "20 Jan 1819", "Naples", titles=[f"{SP} (1788–1808)"])
    child("charles4", "charles3", "ma_saxony")
    person("ml_parma", "Maria Luisa of Parma", "F", "9 Dec 1751", "Parma",
           "2 Jan 1819", "Rome", titles=["Queen of Spain"])
    marry("charles4", "ml_parma", "1765", "", "1819", "death")

    person("ferdinand7", "Ferdinand VII", "M", "14 Oct 1784", "El Escorial, Spain",
           "29 Sep 1833", "Madrid, Spain", titles=[f"{SP} (1808, 1813–1833)"])
    person("carlos_isidro", "Carlos María Isidro, Count of Molina", "M", "29 Mar 1788", "Aranjuez, Spain",
           "10 Mar 1855", "Trieste, Austria", titles=["First Carlist claimant to the Spanish throne"],
           notes="Disputed his niece Isabella II's right to the Spanish throne, starting the Carlist Wars.")
    person("francisco_paula", "Francisco de Paula of Spain", "M", "10 Mar 1794", "Aranjuez, Spain",
           "13 Aug 1865", "Madrid, Spain")
    for k in ("ferdinand7", "carlos_isidro", "francisco_paula"):
        child(k, "charles4", "ml_parma")
    person("mc_two_sicilies", "Maria Christina of the Two Sicilies", "F", "27 Apr 1806", "Palermo, Sicily",
           "22 Aug 1878", "Le Havre, France", titles=["Queen of Spain", "Regent of Spain (1833–1840)"])
    marry("ferdinand7", "mc_two_sicilies", "11 Dec 1829", "Madrid, Spain", "1833", "death",
          notes="Ferdinand's fourth marriage.")

    # ---- The Carlist branch, which held the French claim 1883–1936
    person("montizon", "Juan, Count of Montizón", "M", "15 May 1822", "Aranjuez, Spain",
           "21 Nov 1887", "Hove, England", titles=[f"{LEG} as Jean III (1883–1887)"])
    child("montizon", "carlos_isidro")
    person("carlos_madrid", "Carlos, Duke of Madrid", "M", "30 Mar 1848", "Ljubljana, Austria",
           "18 Jul 1909", "Varese, Italy", titles=[f"{LEG} as Charles XI (1887–1909)", "Carlist claimant to Spain"])
    person("alfonso_carlos", "Alfonso Carlos, Duke of San Jaime", "M", "12 Sep 1849", "London, England",
           "29 Sep 1936", "Vienna, Austria", titles=[f"{LEG} as Charles XII (1931–1936)"],
           notes="The last male of the Carlist line. With no children, the claim passed to Alfonso XIII.")
    child("carlos_madrid", "montizon")
    child("alfonso_carlos", "montizon")
    person("jaime_madrid", "Jaime, Duke of Madrid", "M", "27 Jun 1870", "Vevey, Switzerland",
           "2 Oct 1931", "Paris, France", titles=[f"{LEG} as Jacques I (1909–1931)"],
           notes="Never married; the claim passed to his uncle Alfonso Carlos.")
    child("jaime_madrid", "carlos_madrid")

    # ---- Isabella II and the Spanish royal line
    person("isabella2", "Isabella II", "F", "10 Oct 1830", "Madrid, Spain",
           "9 Apr 1904", "Paris, France", titles=["Queen of Spain (1833–1868)"])
    child("isabella2", "ferdinand7", "mc_two_sicilies")
    person("francisco_asis", "Francisco de Asís, Duke of Cádiz", "M", "13 May 1822", "Aranjuez, Spain",
           "16 Apr 1902", "Épinay-sur-Seine, France", titles=["King consort of Spain"])
    child("francisco_asis", "francisco_paula")
    marry("isabella2", "francisco_asis", "10 Oct 1846", "Madrid, Spain", "1902", "death",
          notes=("Double first cousins: their fathers were brothers and their mothers were sisters. "
                 "The marriage was famously unhappy and they lived apart from 1868."))

    person("alfonso12", "Alfonso XII", "M", "28 Nov 1857", "Madrid, Spain",
           "25 Nov 1885", "El Pardo, Spain", titles=[f"{SP} (1874–1885)"],
           notes=("Legally the son of Francisco de Asís. Contemporaries questioned his paternity; "
                  "the succession has always treated Francisco de Asís as his father."))
    child("alfonso12", "isabella2", "francisco_asis")
    person("mc_austria", "Maria Christina of Austria", "F", "21 Jul 1858", "Židlochovice, Moravia",
           "6 Feb 1929", "Madrid, Spain", titles=["Queen of Spain", "Regent of Spain (1885–1902)"])
    marry("alfonso12", "mc_austria", "29 Nov 1879", "Madrid, Spain", "1885", "death",
          notes="Alfonso's second marriage; his first wife, Mercedes of Orléans, died months after their wedding.")

    person("alfonso13", "Alfonso XIII", "M", "17 May 1886", "Madrid, Spain",
           "28 Feb 1941", "Rome, Italy", titles=[f"{SP} (1886–1931)", f"{LEG} as Alphonse I (1936–1941)"],
           notes="Born king, months after his father's death. Left Spain in 1931 when the Republic was declared.")
    child("alfonso13", "alfonso12", "mc_austria")
    person("ena", "Victoria Eugenie of Battenberg", "F", "24 Oct 1887", "Balmoral Castle, Scotland",
           "15 Apr 1969", "Lausanne, Switzerland", titles=["Queen of Spain"],
           notes="A granddaughter of Queen Victoria, known as Ena.")
    marry("alfonso13", "ena", "31 May 1906", "Madrid, Spain", "1941", "death")

    person("jaime_segovia", "Jaime, Duke of Segovia", "M", "23 Jun 1908", "La Granja de San Ildefonso, Spain",
           "20 Mar 1975", "St. Gallen, Switzerland", titles=[f"{LEG} as Henri VI (1941–1975)"],
           notes=("Deaf from childhood, he renounced his Spanish rights in 1933 in favour of his younger "
                  "brother Juan, but kept the senior position for the French claim."))
    person("juan_barcelona", "Juan, Count of Barcelona", "M", "20 Jun 1913", "La Granja de San Ildefonso, Spain",
           "1 Apr 1993", "Pamplona, Spain", titles=["Head of the Spanish royal house (1941–1977)"])
    child("jaime_segovia", "alfonso13", "ena")
    child("juan_barcelona", "alfonso13", "ena")
    person("dampierre", "Emmanuelle", "F", "8 Nov 1913", "Rome, Italy", "1 May 2012", "Rome, Italy",
           surname="de Dampierre", titles=["Duchess of Segovia"])
    marry("jaime_segovia", "dampierre", "4 Mar 1935", "Rome, Italy", "1947", "divorce",
          notes="Divorced in 1947. Both later remarried.")

    person("juan_carlos", "Juan Carlos I", "M", "5 Jan 1938", "Rome, Italy",
           titles=[f"{SP} (1975–2014)"])
    child("juan_carlos", "juan_barcelona")
    person("felipe6", "Felipe VI", "M", "30 Jan 1968", "Madrid, Spain", titles=[f"{SP} (2014–)"])
    child("felipe6", "juan_carlos")

    # ---- The present claimant
    person("cadiz", "Alfonso, Duke of Anjou and Cádiz", "M", "20 Apr 1936", "Rome, Italy",
           "30 Jan 1989", "Beaver Creek, Colorado, USA",
           titles=[f"{LEG} as Alphonse II (1975–1989)"],
           notes="Died in a skiing accident.")
    child("cadiz", "jaime_segovia", "dampierre")
    person("carmen", "Carmen", "F", "26 Feb 1951", "Madrid, Spain", surname="Martínez-Bordiú",
           notes="Granddaughter of Francisco Franco.")
    marry("cadiz", "carmen", "8 Mar 1972", "El Pardo, Spain", "1986", "annulment",
          notes="Separated in 1982; the Catholic marriage was annulled in 1986.")
    person("fran", "Francisco", "M", "22 Nov 1972", "Madrid, Spain", "7 Feb 1984", "",
           surname="de Borbón", titles=["Duke of Bourbon"],
           notes="Killed at eleven in a car crash in which his father was driving and his brother was injured.")
    person("louis20", "Louis Alphonse", "M", "25 Apr 1974", "Madrid, Spain", surname="de Bourbon",
           titles=[f"{LEG} as Louis XX (1989–)", "Duke of Anjou"],
           notes=("Senior male-line descendant of Louis XIV, through Philip V. Orléanists support a rival "
                  "claimant from the Orléans branch, so the claim is disputed."))
    child("fran", "cadiz", "carmen")
    child("louis20", "cadiz", "carmen")
    person("margarita", "Margarita", "F", "21 Oct 1983", "Caracas, Venezuela", surname="Vargas Santaella",
           titles=["Duchess of Anjou"])
    marry("louis20", "margarita", "5 Nov 2004", "Caracas, Venezuela",
          notes="Civil wedding in Caracas; religious wedding the next day in La Romana, Dominican Republic.")
    for key, given, sex, year in (("eugenia", "Eugenia", "F", "2007"), ("luis", "Luis", "M", "2010"),
                                  ("alfonso", "Alfonso", "M", "2010"), ("henri", "Henri", "M", "2019")):
        person(key, given, sex, year, surname="de Borbón")
        child(key, "louis20", "margarita")
    store.save_person({"notes": "Twin of Alfonso. Heir to the Legitimist claim as Duke of Burgundy."}, P["luis"])
    store.save_person({"notes": "Twin of Luis."}, P["alfonso"])

    # ---- Stories
    store.save_story({
        "title": "How a French claim came to rest in Spain", "date": "1713–1989",
        "told_by": "Heirloom example",
        "body": ("Under the old French rule, the crown passed to the eldest son, then through male "
                 "descendants only, and could not be given up.\n\n"
                 "In 1713 Philip V, Louis XIV's grandson and already King of Spain, renounced his French "
                 "rights as the price of peace. When the senior French line ended with the Count of "
                 "Chambord in 1883, the Legitimists argued that the renunciation had never been valid, "
                 "so the claim belonged to Philip's senior male descendant.\n\n"
                 "That was the Carlist branch until it died out in 1936. It then passed to Alfonso XIII, "
                 "to his eldest son Jaime, Duke of Segovia, to Jaime's son Alfonso, and in 1989 to "
                 "Louis Alphonse.\n\n"
                 "Orléanists disagree. They say the renunciation stands, which makes the head of the "
                 "Orléans branch the heir."),
        "person_ids": [P[k] for k in ("louis14", "philip5", "chambord", "montizon", "alfonso_carlos",
                                      "alfonso13", "jaime_segovia", "cadiz", "louis20")],
    })
    store.save_story({
        "title": "February 1984", "date": "1984",
        "told_by": "Heirloom example",
        "body": ("In February 1984 Alfonso was driving his two sons when the car crashed. "
                 "Francisco, eleven, died of his injuries; Louis Alphonse, nine, survived. "
                 "Five years later Alfonso himself died in a skiing accident in Colorado, "
                 "and the fourteen-year-old Louis Alphonse became head of the line."),
        "person_ids": [P["cadiz"], P["fran"], P["louis20"]],
    })
    store.set_meta("family_name", "The Bourbon Succession")
    return P


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bourbon-succession.ged")
    with tempfile.TemporaryDirectory() as tmp:
        s = Store(tmp)
        P = build(s)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(export_gedcom(s))
        s.conn.close()
    print(f"{len(P)} people written to {out}")
