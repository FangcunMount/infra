"""Explicit C08 candidates; never change the frozen C06 rehearsal defaults."""
import hashlib
import json
from pathlib import Path
import re

from image_start_fixture import require

TARGETS = ('iam', 'qs-api', 'qs-collection', 'qs-worker', 'ai')
SDK = dict(go='v0.5.0', python='0.4.0', source_sha='1345266aa0e864c46de5d1e3e3c939dd8002a890')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate_final_candidate_field')
        result[key] = value
    return result


def parse(raw):
    require(isinstance(raw, bytes) and 0 < len(raw) <= 65536, 'bounded_final_candidate_manifest_required')
    value = json.loads(raw, object_pairs_hook=unique_object)
    require(set(value) == {'schema', 'sources', 'builder_sha', 'image_runs', 'sdk', 'production', 'scope'}
            and value['schema'] == 'm4-final-image-candidates/v1', 'exact_final_candidate_schema_required')
    require(isinstance(value['sources'], dict) and set(value['sources']) == {'iam', 'qs', 'ai'},
            'three_exact_final_source_roles_required')
    for source in [value['builder_sha'], *value['sources'].values()]:
        require(isinstance(source, str) and re.fullmatch('[a-f0-9]{40}', source), 'immutable_final_source_required')
    require(isinstance(value['image_runs'], dict) and set(value['image_runs']) == set(TARGETS),
            'five_exact_final_archives_required')
    require(all(isinstance(x, str) and re.fullmatch('[1-9][0-9]{8,15}', x)
                for x in value['image_runs'].values()), 'immutable_image_build_run_required')
    require(len({value['image_runs'][x] for x in TARGETS if x.startswith('qs-')}) == 1,
            'one_coordinated_qs_build_required')
    require(value['sdk'] == SDK, 'published_stable_sdk_unchanged')
    require(value['production'] is False and isinstance(value['scope'], str) and value['scope'],
            'candidate_is_not_production_acceptance')
    return value


def read(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'regular_final_candidate_manifest_required')
    raw = path.read_bytes()
    value = parse(raw)
    return value, hashlib.sha256(raw).hexdigest()
