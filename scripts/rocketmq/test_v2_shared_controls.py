import unittest

from v2_acceptance import shared_budget


class Observer:
    def __init__(self, ids):
        self.ids=ids;self.events=[];self.released=self.ready=self.finished=False

    def wait(self,event,identity=None,timeout=90):
        if event=='ready':self.ready=True
        if event=='received' and not any(e.get('event')=='received' and e.get('id')==identity for e in self.events):
            raise AssertionError('not actually released')

    def drain(self):
        if not self.events:
            self.events=[dict(event='handler_enter',id=identity,decision=str(i+1)) for i,identity in enumerate(self.ids[:2])]

    def send(self,value):
        if value=='release':
            self.released=True
            self.events.extend(dict(event='received',id=identity) for identity in self.ids)
        if value=='stop':self.events.append(dict(event='max_inflight',decision='2'))

    def finish(self):self.finished=True


class Sender:
    def wait(self,*args,**kwargs):pass
    def send(self,*args):pass
    def finish(self):pass


class SharedControlBoundaryTest(unittest.TestCase):
    def run_case(self,callback=None):
        self.ids=[];self.observer=None;self.passed=[]
        def start(language,mode,identity='',**options):
            if mode=='shared-consume':self.observer=Observer(self.ids);return self.observer
            self.ids.extend(identity+'-b'+str(i) for i in range(3));return Sender()
        shared_budget(start,self.passed.append,language='sdk-go',observe=callback)

    def test_legacy_default_keeps_original_one_receipt_and_shared_budget(self):
        self.run_case()
        self.assertTrue(self.observer.finished)
        self.assertEqual(len(self.ids),9)
        self.assertEqual(self.passed,['v2_sdk-go_three_physical_inputs_share_two_handler_budget'])

    def test_registration_query_precedes_publication_and_held_audit_precedes_ack_release(self):
        stages=[]
        def observe(stage,language):
            self.assertEqual(language,'sdk-go');stages.append(stage)
            if stage=='baseline':self.assertIsNone(self.observer)
            elif stage=='subscribed':self.assertTrue(self.observer.ready);self.assertEqual(self.ids,[])
            elif stage=='held':self.assertFalse(self.observer.released);self.assertEqual(len(self.observer.events),2)
            elif stage=='closed':self.assertTrue(self.observer.finished);self.assertEqual(self.passed,[])
        self.run_case(observe)
        self.assertEqual(stages,['baseline','subscribed','held','closed'])

    def test_failed_held_audit_cannot_release_or_report_success(self):
        def observe(stage,language):
            if stage=='held':raise RuntimeError('controlled incomplete metrics')
        with self.assertRaisesRegex(RuntimeError,'incomplete metrics'):self.run_case(observe)
        self.assertFalse(self.observer.released)
        self.assertEqual(self.passed,[])
