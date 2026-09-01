import unittest
from astermax.updated_surface_contact import UpdatedSurfaceContactError, _search

class UpdatedClosestFeatureHarness(unittest.TestCase):
    def setUp(self):
        # Two coplanar TRI3s sharing the x=1 edge. Slave lies above the shared edge.
        self.points=((1.0,0.5,0.2),(0,0,0),(1,0,0),(1,1,0),(2,0,0),(2,1,0))
        self.tris=((1,2,3),(2,4,5))
        self.hint=(0.0,0.0,1.0)
    def test_closest_feature_keeps_edge_association_deterministic(self):
        a,u=_search(self.points,[0],self.tris,self.hint,0.3,1e-10,"closest_feature")
        b,v=_search(self.points,[0],tuple(reversed(self.tris)),self.hint,0.3,1e-10,"closest_feature")
        self.assertEqual(u,()); self.assertEqual(v,()); self.assertEqual(a,b)
        self.assertAlmostEqual(abs(a[0].gap),0.2,places=12)
        self.assertAlmostEqual(sum(a[0].barycentric),1.0,places=12)
    def test_strict_policy_remains_available(self):
        found,unmatched=_search(self.points,[0],self.tris,self.hint,0.3,1e-10,"strict")
        self.assertEqual(unmatched,()); self.assertEqual(len(found),1)
    def test_closest_feature_survives_small_tangential_crossing(self):
        left=((0.99,0.5,0.2),)+self.points[1:]
        right=((1.01,0.5,0.2),)+self.points[1:]
        a,_=_search(left,[0],self.tris,self.hint,0.3,1e-10,"closest_feature")
        b,_=_search(right,[0],self.tris,self.hint,0.3,1e-10,"closest_feature")
        self.assertEqual(len(a),1); self.assertEqual(len(b),1)
        self.assertAlmostEqual(abs(a[0].gap),0.2,places=12); self.assertAlmostEqual(abs(b[0].gap),0.2,places=12)
    def test_search_distance_fails_closed(self):
        found,unmatched=_search(self.points,[0],self.tris,self.hint,0.1,1e-10,"closest_feature")
        self.assertEqual(found,()); self.assertEqual(unmatched,(0,))

if __name__=='__main__': unittest.main()
