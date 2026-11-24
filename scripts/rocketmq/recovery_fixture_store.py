"""Read-only projections for CI-owned original recovery databases, never runtime stores.

Actual decisions and CAS stay in the compiled Go authority/SDK. These adapters
only assert fixture counts/governance/audit without exporting bodies or tokens.
"""
import json
import re


class SQLFixtureStore:
    def __init__(self,sql,business_count_sql):self.sql,self.business_count_sql=sql,business_count_sql
    def governance(self):return self.sql("SELECT HEX(notice_key),HEX(evidence_sha256),status,IFNULL(HEX(resolution_receipt_sha256),'') FROM messaging_native_limit_notices ORDER BY notice_key;")
    def counts(self):return self.sql('SELECT ('+self.business_count_sql+'),(SELECT COUNT(*) FROM rm_tx_request),(SELECT COUNT(*) FROM rm_tx_execution),(SELECT COUNT(*) FROM rm_tx_witness);')
    def audit(self):return self.sql("SELECT final_outcome,DATE_FORMAT(final_recorded_at,'%Y-%m-%dT%H:%i:%s.%f') FROM rm_tx_witness;")


class MongoFixtureStore:
    def __init__(self,query,database):
        if not isinstance(database,str) or not re.fullmatch(r'qs_m3_host_[0-9]{10,30}',database):raise RuntimeError('owned_original_mongo_database_required')
        self.query,self.database=query,database
    def read(self,expression):
        return json.loads(self.query('const original=db.getSiblingDB('+json.dumps(self.database)+');JSON.stringify('+expression+')'))
    def governance(self):
        return self.read('(()=>{const rows=original.messaging_native_limit_notices.find({}, {_id:1,evidence_sha256:1,status:1,resolution_receipt_sha256:1}).limit(2).toArray();if(rows.length!==1)throw new Error("single_owned_notice_required");const r=rows[0];const h=v=>v?Buffer.from(EJSON.serialize(v).$binary.base64,"base64").toString("hex").toUpperCase():"";return [h(r._id),h(r.evidence_sha256),r.status,h(r.resolution_receipt_sha256)].join("\\t").trimEnd()})()')
    def counts(self):
        value=self.read('[original.m3_owner_runtime_facts.countDocuments({}),original.rm_tx_request.countDocuments({}),original.rm_tx_execution.countDocuments({}),original.rm_tx_execution.aggregate([{$project:{n:{$size:"$witnesses"}}},{$group:{_id:null,n:{$sum:"$n"}}}]).toArray()[0]?.n??0]')
        if not isinstance(value,list) or len(value)!=4 or any(type(n) is not int or n<0 for n in value):raise RuntimeError('exact_owned_mongo_counts_required')
        return '\t'.join(map(str,value))
    def audit(self):
        return self.read('(()=>{const r=original.rm_tx_execution.findOne({}, {_id:0,"witnesses.final_outcome":1,"witnesses.final_recorded_at":1});if(!r||r.witnesses.length!==1)throw new Error("single_owned_witness_required");const w=r.witnesses[0];return w.final_outcome+"\\t"+(w.final_recorded_at?w.final_recorded_at.toISOString():"")})()')
