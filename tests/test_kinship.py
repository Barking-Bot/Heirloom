import tempfile
import unittest

from heirloom.db import Store
from heirloom.kinship import relationship, name_route
from heirloom.sample import load_sample


class NamingTests(unittest.TestCase):
    def test_names(self):
        self.assertEqual(name_route(1, 0, "M"), "father")
        self.assertEqual(name_route(3, 0, "F"), "great-grandmother")
        self.assertEqual(name_route(5, 0, "U"), "3rd great-grandparent")
        self.assertEqual(name_route(0, 2, "F"), "granddaughter")
        self.assertEqual(name_route(1, 1, "M"), "brother")
        self.assertEqual(name_route(1, 1, "M", half=True), "half-brother")
        self.assertEqual(name_route(2, 1, "F"), "aunt")
        self.assertEqual(name_route(3, 1, "M"), "great-uncle")
        self.assertEqual(name_route(1, 3, "F"), "great-niece")
        self.assertEqual(name_route(2, 2), "first cousin")
        self.assertEqual(name_route(3, 3), "second cousin")
        self.assertEqual(name_route(3, 2), "first cousin once removed")
        self.assertEqual(name_route(5, 3), "second cousin twice removed")


class SampleFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = Store(cls.tmp.name)
        cls.P = load_sample(cls.store)
        cls.g = cls.store.graph()

    @classmethod
    def tearDownClass(cls):
        cls.store.conn.close()
        cls.tmp.cleanup()

    def rel(self, a, b):
        return relationship(self.g, self.P[a], self.P[b])

    def test_adopted_second_cousin(self):
        r = self.rel("emma", "samuel")
        self.assertEqual(r["legal"][0]["label"], "brother")
        self.assertFalse(r["legal"][0]["half"])
        self.assertEqual(r["genetic"][0]["label"], "second cousin")
        self.assertIn("by blood", r["summary"].lower())
        self.assertIn("second cousin", r["summary"])

    def test_adoption_replaces_birth_parents_legally(self):
        r = self.rel("samuel", "peter")
        self.assertEqual(r["genetic"][0]["label"], "father")
        # Legally his birth father is now his adoptive father's first cousin.
        self.assertEqual(r["legal"][0]["label"], "first cousin once removed")
        self.assertTrue(r["summary"].startswith("By blood, Peter Doyle is Samuel Hayes's father"))
        r = self.rel("samuel", "george")
        self.assertEqual(r["legal"][0]["label"], "father")

    def test_birth_family_cousin(self):
        self.assertEqual(self.rel("george", "peter")["genetic"][0]["label"], "first cousin")
        self.assertEqual(self.rel("samuel", "margaret")["genetic"][0]["label"], "grandmother")
        self.assertEqual(self.rel("samuel", "margaret")["legal"][0]["label"], "great-aunt")

    def test_maiden_name(self):
        ruth = self.store.summary(self.P["ruth"])
        self.assertEqual(ruth["display_name"], "Ruth Ann Hayes")
        self.assertEqual(ruth["nee"], "Miller")
        emma = self.store.summary(self.P["emma"])
        self.assertEqual(emma["display_name"], "Emma Okafor")

    def test_step_and_spouse(self):
        self.assertIn("stepfather", self.rel("lucy", "dan")["other"])
        self.assertIn("stepdaughter", self.rel("dan", "lucy")["other"])
        self.assertIn("former husband", self.rel("emma", "tom")["other"])
        self.assertIn("husband", self.rel("emma", "dan")["other"])

    def test_in_laws(self):
        self.assertIn("father-in-law", self.rel("dan", "george")["other"])
        self.assertIn("son-in-law", self.rel("george", "dan")["other"])
        self.assertIn("mother-in-law", self.rel("tom", "linda")["other"])

    def test_ancestor(self):
        self.assertEqual(self.rel("lucy", "walter")["genetic"][0]["label"],
                         "great-great-grandfather")


class TrickyShapes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = Store(self.tmp.name)

    def tearDown(self):
        self.s.conn.close()
        self.tmp.cleanup()

    def p(self, name, sex="U"):
        return self.s.save_person({"given_names": name, "sex": sex})

    def test_half_siblings(self):
        mom, d1, d2 = self.p("Mom", "F"), self.p("Dad1", "M"), self.p("Dad2", "M")
        a, b = self.p("A"), self.p("B", "F")
        for c, d in ((a, d1), (b, d2)):
            self.s.add_parent_link(c, mom)
            self.s.add_parent_link(c, d)
        self.s.save_couple({"partner1_id": mom, "partner2_id": d1})
        self.s.save_couple({"partner1_id": mom, "partner2_id": d2})
        r = relationship(self.s.graph(), a, b)
        self.assertEqual(r["genetic"][0]["label"], "half-sister")

    def test_pedigree_collapse_double_relationship(self):
        # First cousins marry; their child is related to a grandparent's line twice.
        gp, gm = self.p("GP", "M"), self.p("GM", "F")
        self.s.save_couple({"partner1_id": gp, "partner2_id": gm})
        s1, s2 = self.p("S1", "M"), self.p("S2", "F")
        for s in (s1, s2):
            self.s.add_parent_link(s, gp)
            self.s.add_parent_link(s, gm)
        c1, c2 = self.p("C1", "M"), self.p("C2", "F")
        self.s.add_parent_link(c1, s1)
        self.s.add_parent_link(c2, s2)
        self.s.save_couple({"partner1_id": c1, "partner2_id": c2})
        kid = self.p("Kid")
        self.s.add_parent_link(kid, c1)
        self.s.add_parent_link(kid, c2)
        r = relationship(self.s.graph(), kid, c1)
        self.assertEqual(r["genetic"][0]["label"], "father")
        labels = [x["label"] for x in r["genetic"]]
        self.assertIn("first cousin once removed", labels)
        self.assertEqual(relationship(self.s.graph(), kid, gp)["genetic"][0]["label"],
                         "great-grandfather")

    def test_step_parent_adoption_keeps_other_parent(self):
        mom, dad, step = self.p("Mom", "F"), self.p("Dad", "M"), self.p("Step", "M")
        kid = self.p("Kid")
        self.s.add_parent_link(kid, mom)
        self.s.add_parent_link(kid, dad)
        self.s.save_couple({"partner1_id": mom, "partner2_id": step})
        self.s.add_parent_link(kid, step, "adoptive")
        g = self.s.graph()
        self.assertEqual(relationship(g, kid, mom)["legal"][0]["label"], "mother")
        self.assertEqual(relationship(g, kid, step)["legal"][0]["label"], "father")
        self.assertEqual(relationship(g, kid, dad)["legal"], [])
        self.assertEqual(relationship(g, kid, dad)["genetic"][0]["label"], "father")

    def test_no_cycles(self):
        a, b = self.p("A"), self.p("B")
        self.s.add_parent_link(b, a)
        with self.assertRaises(Exception):
            self.s.add_parent_link(a, b)


if __name__ == "__main__":
    unittest.main()
