import copy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('cutover',Path(__file__).with_name('ai_cutover.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class ContractTest(unittest.TestCase):
    def pair(self):
        old={'services':{'qs-ai':{'image':'old','environment':{'QS_AI_DATABASE_URL':'mysql+asyncmy://u:p%40%24@mysql-rds-proxy:3306/ai','MQ':'unchanged'},'volumes':[],'mem_limit':'768m'}}}
        new=copy.deepcopy(old);s=new['services']['qs-ai'];s['image']='new';s['volumes'].append(m.CA)
        s['environment'].update(QS_AI_DATABASE_URL='mysql+asyncmy://u:p%40%24@public.mysql.example:3306/ai',QS_AI_DATABASE_TLS_MODE='VERIFY_IDENTITY',QS_AI_DATABASE_TLS_CA_FILE=m.CA['target'],MYSQL_TLS_CA_REF='a'*40)
        return old,new

    def test_connection_only_change_is_accepted(self):
        m.connection_only(*self.pair())

    def test_business_or_resource_change_is_rejected(self):
        for kind in ('memory','messages','credentials'):
            old,new=self.pair();s=new['services']['qs-ai']
            if kind=='memory':s['mem_limit']='1g'
            if kind=='messages':s['environment']['MQ']='different'
            if kind=='credentials':s['environment']['QS_AI_DATABASE_URL']=s['environment']['QS_AI_DATABASE_URL'].replace('p%40%24','different')
            with self.assertRaises(ValueError):m.connection_only(old,new)


if __name__=='__main__':unittest.main()
