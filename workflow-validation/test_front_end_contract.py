"""Checks reject configurations that could silently change intent or waste a task."""
import copy
import json
import unittest
from front_end_contract import HERE, VIEWS, build_request, validate_parameters


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((HERE / "front-end-profile.json").read_text())
        self.params = copy.deepcopy(self.profile["tripo"]["request_parameters"])
        self.views = {v: f"file_test_{v}" for v in VIEWS}

    def test_baseline_and_variants(self):
        for name, overrides in {"baseline": {}, **self.profile["tripo"]["variants"]}.items():
            with self.subTest(name=name):
                request = build_request({**self.params, **overrides}, self.views)
                self.assertEqual([next(iter(x)) for x in request["inputs"]], list(VIEWS))

    def test_reject_legacy_and_invented_fields(self):
        for field in ("model_version", "type", "files", "prompt", "negative_prompt", "texture_resolution"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_parameters({**self.params, field: "unused"})

    def test_reject_ignored_delight_and_unsupported_fast(self):
        for override in ({"delight": True}, {"texture_quality": "fast"}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                validate_parameters({**self.params, **override})

    def test_reject_conflicting_topology_and_parts(self):
        for override in ({"generate_parts": True}, {"quad": True}, {"pbr": True}, {"face_limit": 20001}, {"face_limit": True}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                validate_parameters({**self.params, **override})

    def test_reject_missing_or_duplicate_views(self):
        for views in ({k: v for k, v in self.views.items() if k != "front"},
                      {**self.views, "left": self.views["right"]},
                      {**self.views, "left": ""}):
            with self.subTest(views=views), self.assertRaises(ValueError):
                build_request(self.params, views)

    def test_reject_misleading_compression_boolean(self):
        with self.assertRaises(ValueError):
            validate_parameters({**self.params, "compress": False})

    def test_input_config_not_mutated(self):
        before = copy.deepcopy(self.params)
        request = build_request(self.params, self.views)
        request["face_limit"] = 6000
        self.assertEqual(self.params, before)


if __name__ == "__main__":
    unittest.main()
