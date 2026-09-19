"""Exercise reporting with synthetic audit metadata only, never synthetic FEA."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path
BUILDER = Path(__file__).with_name('build-report.py')
class ReportGateTests(unittest.TestCase):
    def run_report(self, session, present=True):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            contract={'stages':[{'id':'solution','mandatory':True,'evidence':['proof.json']}], 'cross_cutting_checks':['pmx']}
            (root/'contract.json').write_text(json.dumps(contract));(root/'session.json').write_text(json.dumps(session))
            if present:(root/'proof.json').write_text('{}')
            subprocess.run([sys.executable,str(BUILDER),'--contract',str(root/'contract.json'),'--session',str(root/'session.json'),'--outdir',str(root)],check=True,capture_output=True)
            return json.loads((root/'workflow-conformance-report.json').read_text())
    def good(self):
        return {'pass':True,'process_exit_code':0,'rows':[{'stage':'solution','status':'PASS'}],'cross_cutting':{'checks':[{'id':'pmx','status':'PASS'}]}}
    def test_complete(self):self.assertTrue(self.run_report(self.good())['summary']['release_gate_pass'])
    def test_partial(self):
        s=self.good();s['partial']=True;self.assertFalse(self.run_report(s)['summary']['release_gate_pass'])
    def test_crash(self):
        s=self.good();s['process_exit_code']=-1073740771;self.assertFalse(self.run_report(s)['summary']['release_gate_pass'])
    def test_error(self):
        s=self.good();s['error']='PMX failed';self.assertFalse(self.run_report(s)['summary']['release_gate_pass'])
    def test_missing_proof(self):self.assertFalse(self.run_report(self.good(),False)['summary']['release_gate_pass'])
    def test_missing_cross(self):
        s=self.good();s.pop('cross_cutting');self.assertFalse(self.run_report(s)['summary']['release_gate_pass'])
    def test_explicit_fail_without_proof(self):
        s=self.good();s['rows'][0]['status']='FAIL';r=self.run_report(s,False);self.assertEqual(r['summary']['mandatory_failures'],1)
if __name__=='__main__':unittest.main()
