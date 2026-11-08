import tempfile
import unittest

from heirloom.db import Store
from heirloom.gedcom import export_gedcom, import_gedcom
from heirloom.kinship import relationship
from heirloom.sample import load_sample

ANCESTRY_STYLE = """0 HEAD
1 SOUR Ancestry.com Family Trees
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Smith/
1 SEX M
1 BIRT
2 DATE 3 FEB 1950
2 PLAC Austin, Texas, USA
1 OCCU Carpenter
1 FAMS @F1@
0 @I2@ INDI
1 NAME Mary /Jones/
2 _MARNM Smith
1 SEX F
1 FAMS @F1@
0 @I3@ INDI
1 NAME Kate /Smith/
1 SEX F
1 FAMC @F1@
0 @I4@ INDI
1 NAME Ben /Smith/
1 SEX M
1 FAMC @F1@
1 NOTE Loved fishing with his
2 CONC  grandfather.
2 CONT Second line.
0 @I5@ INDI
1 NAME Ann /Smith/
1 SEX F
1 FAMC @F1@
2 PEDI foster
1 DEAT Y
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1975
1 CHIL @I3@
2 _FREL Natural
2 _MREL Natural
1 CHIL @I4@
2 _FREL Adopted
2 _MREL Natural
1 CHIL @I5@
0 TRLR
"""


class GedcomTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = Store(self.tmp.name)

    def tearDown(self):
        self.s.conn.close()
        self.tmp.cleanup()

    def by_name(self, store=None):
        return {p["given_names"]: p for p in (store or self.s).list_people()}

    def test_ancestry_import(self):
        counts = import_gedcom(self.s, ANCESTRY_STYLE)
        self.assertEqual(counts["people"], 5)
        P = self.by_name()
        self.assertEqual(P["Mary"]["display_name"], "Mary Smith")
        self.assertEqual(P["Mary"]["nee"], "Jones")
        ben = self.s.get_person(P["Ben"]["id"])
        kinds = {l["person"]["given_names"]: l["kind"] for l in ben["parents"]}
        self.assertEqual(kinds, {"John": "adoptive", "Mary": "biological"})
        self.assertEqual(ben["notes"], "Loved fishing with his grandfather.\nSecond line.")
        ann = self.s.get_person(P["Ann"]["id"])
        self.assertEqual({l["kind"] for l in ann["parents"]}, {"foster"})
        self.assertTrue(ann["deceased"])
        john = self.s.get_person(P["John"]["id"])
        self.assertEqual(john["facts"][0]["detail"], "Carpenter")
        self.assertEqual(john["birth_place"], "Austin, Texas, USA")

    def test_round_trip_sample(self):
        P = load_sample(self.s)
        text = export_gedcom(self.s)
        self.assertIn("2 _FREL Adopted", text)
        self.assertIn("2 PEDI adopted", text)

        tmp2 = tempfile.TemporaryDirectory()
        s2 = Store(tmp2.name)
        try:
            import_gedcom(s2, text)
            self.assertEqual(len(s2.list_people()), len(self.s.list_people()))
            Q = {p["display_name"]: p["id"] for p in s2.list_people()}
            g = s2.graph()
            r = relationship(g, Q["Emma Okafor"], Q["Samuel Hayes"])
            self.assertEqual(r["legal"][0]["label"], "brother")
            self.assertEqual(r["genetic"][0]["label"], "second cousin")
            r = relationship(g, Q["Lucy Reyes"], Q["Daniel Okafor"])
            self.assertIn("stepfather", r["other"])
            r = relationship(g, Q["Emma Okafor"], Q["Tom Reyes"])
            self.assertIn("former husband", r["other"])
            stories = s2.list_stories()
            self.assertEqual(len(stories), 1)
            self.assertEqual(stories[0]["title"], "The winter of 1980")
            self.assertEqual(stories[0]["told_by"], "Linda Hayes")
            self.assertEqual(len(stories[0]["person_ids"]), 5)
        finally:
            s2.conn.close()
            tmp2.cleanup()


if __name__ == "__main__":
    unittest.main()
