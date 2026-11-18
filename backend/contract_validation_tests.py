"""
Contract validation tests for the NoodleAttributes-based data contracts.
Validates that nodes produce correctly serialized outputs and that the
NoodleAttributes / CollectionSpec / CollectionInstanceSpec / GeometryEnvelope
round-trip cleanly.
"""

import sys
from pathlib import Path

try:
    from .contracts import (
        NoodleAttributes, CollectionSpec, CollectionInstanceSpec, GeometryEnvelope, Vector3Spec
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from backend.contracts import (
        NoodleAttributes, CollectionSpec, CollectionInstanceSpec, GeometryEnvelope, Vector3Spec
    )


# ---------------------------------------------------------------------------
# Individual tests
# ---------------------------------------------------------------------------

def test_noodle_attributes_serialization():
    """NoodleAttributes round-trips cleanly through to_dict / from_dict."""
    errors = []

    # Identity
    identity = NoodleAttributes.identity()
    if not hasattr(identity, 'to_dict'):
        errors.append("NoodleAttributes.identity() missing to_dict()")
        return errors

    d = identity.to_dict()
    if not isinstance(d, dict):
        errors.append(f"NoodleAttributes.to_dict() returned {type(d)}, expected dict")
        return errors

    required = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'qx', 'qy', 'qz', 'qw', 'use_quaternion']
    for key in required:
        if key not in d:
            errors.append(f"NoodleAttributes dict missing key: {key}")

    # Quaternion round-trip
    quat = NoodleAttributes(
        tx=1.0, ty=2.0, tz=3.0,
        rx=0.0, ry=0.0, rz=0.0,
        sx=0.5, sy=0.5, sz=0.5,
        qx=0.0, qy=0.7071, qz=0.0, qw=0.7071,
        use_quaternion=True,
    )
    qd = quat.to_dict()
    rebuilt = NoodleAttributes(**qd)
    if abs(rebuilt.tx - 1.0) > 1e-6 or abs(rebuilt.sy - 0.5) > 1e-6:
        errors.append("NoodleAttributes quaternion round-trip lost values")

    # from_dict
    try:
        back = NoodleAttributes.from_dict(d)
        if not isinstance(back, NoodleAttributes):
            errors.append(f"NoodleAttributes.from_dict returned {type(back)}")
    except Exception as e:
        errors.append(f"NoodleAttributes.from_dict failed: {e}")

    return errors


def test_collection_instance_spec_serialization():
    """CollectionInstanceSpec with NoodleAttributes transform serializes correctly."""
    errors = []

    attrs = NoodleAttributes.identity()
    inst = CollectionInstanceSpec(
        instance_id="inst_001",
        source_geometry_id="geo_001",
        transform=attrs,
        metadata={"index": 0},
    )

    if not hasattr(inst, 'to_dict'):
        errors.append("CollectionInstanceSpec missing to_dict()")
        return errors

    d = inst.to_dict()
    if not isinstance(d, dict):
        errors.append(f"CollectionInstanceSpec.to_dict() returned {type(d)}")
        return errors

    for key in ['instance_id', 'source_geometry_id', 'transform', 'metadata']:
        if key not in d:
            errors.append(f"CollectionInstanceSpec dict missing key: {key}")

    if isinstance(d.get('transform'), dict):
        if 'tx' not in d['transform']:
            errors.append("Serialized transform missing 'tx' — not NoodleAttributes format")
    else:
        errors.append(f"Serialized transform is {type(d.get('transform'))}, expected dict")

    # from_dict round-trip
    try:
        back = CollectionInstanceSpec.from_dict(d)
        if not isinstance(back, CollectionInstanceSpec):
            errors.append(f"CollectionInstanceSpec.from_dict returned {type(back)}")
    except Exception as e:
        errors.append(f"CollectionInstanceSpec.from_dict failed: {e}")

    return errors


def test_collection_spec_serialization():
    """CollectionSpec serializes a list of CollectionInstanceSpec objects correctly."""
    errors = []

    geo = GeometryEnvelope(kind="box", id="geo_001", geometry=None, geometry_name="TestBox", metadata={})
    instances = [
        CollectionInstanceSpec(
            instance_id=f"inst_{i:03d}",
            source_geometry_id="geo_001",
            transform=NoodleAttributes.identity(),
            metadata={"index": i},
        )
        for i in range(3)
    ]

    try:
        col = CollectionSpec(
            collection_type="geometry_collection",
            collection_id="test_col",
            source_geometries=[geo],
            instances=instances,
        )
    except Exception as e:
        errors.append(f"CollectionSpec construction failed: {e}")
        return errors

    d = col.to_dict()
    if not isinstance(d, dict):
        errors.append(f"CollectionSpec.to_dict() returned {type(d)}")
        return errors

    if not isinstance(d.get('instances'), list):
        errors.append("CollectionSpec dict 'instances' is not a list")
    elif len(d['instances']) != 3:
        errors.append(f"Expected 3 instances, got {len(d['instances'])}")
    else:
        for i, inst_d in enumerate(d['instances']):
            if not isinstance(inst_d, dict):
                errors.append(f"Instance {i} in serialized collection is {type(inst_d)}, expected dict")

    # from_dict round-trip
    try:
        back = CollectionSpec.from_dict(d)
        if len(back.instances) != 3:
            errors.append(f"CollectionSpec.from_dict produced {len(back.instances)} instances, expected 3")
    except Exception as e:
        errors.append(f"CollectionSpec.from_dict failed: {e}")

    return errors


def test_dict_instances_rejected():
    """CollectionSpec must reject raw dicts as instances (catches the old regression)."""
    errors = []

    attrs = NoodleAttributes.identity()
    inst = CollectionInstanceSpec(
        instance_id="inst_001", source_geometry_id="geo_001",
        transform=attrs, metadata={},
    )

    try:
        col = CollectionSpec(
            collection_type="geometry_collection",
            collection_id="bad_col",
            source_geometries=[],
            instances=[inst.to_dict()],  # dict instead of object
        )
        # If construction didn't raise, check that to_dict() fails
        try:
            col.to_dict()
            errors.append("REGRESSION: dict instance accepted without error — old bug has returned")
        except (AttributeError, TypeError):
            pass  # expected
    except (AttributeError, TypeError):
        pass  # also fine — rejected at construction time
    except Exception as e:
        errors.append(f"Unexpected error: {e}")

    return errors


def test_noodle_attributes_composition():
    """Component-wise transform composition preserves position and scale independently."""
    errors = []

    # Simulate a surface-placed instance at world position (5, 0, 3) with identity quaternion
    base = NoodleAttributes(
        tx=5.0, ty=0.0, tz=3.0,
        rx=0.0, ry=0.0, rz=0.0,
        sx=1.0, sy=1.0, sz=1.0,
        qx=0.0, qy=0.0, qz=0.0, qw=1.0,
        use_quaternion=True,
    )

    # Effector: scale down to 0.5
    effector = NoodleAttributes(
        tx=0.0, ty=0.0, tz=0.0,
        rx=0.0, ry=0.0, rz=0.0,
        sx=0.5, sy=0.5, sz=0.5,
    )

    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from backend.services.transform_composition_service import TransformCompositionService
        svc = TransformCompositionService()
        result = svc.compose_noodle_attributes(base, effector)

        if abs(result.tx - 5.0) > 1e-6 or abs(result.tz - 3.0) > 1e-6:
            errors.append(f"Scale effector moved position: tx={result.tx}, tz={result.tz} (expected 5, 3)")
        if abs(result.sx - 0.5) > 1e-6:
            errors.append(f"Scale not applied: sx={result.sx} (expected 0.5)")
    except Exception as e:
        errors.append(f"Composition test failed: {e}")

    return errors


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_contract_validation_tests():
    """Run all contract validation tests. Returns list of (test_name, [errors])."""
    tests = [
        ("NoodleAttributes Serialization",       test_noodle_attributes_serialization),
        ("CollectionInstanceSpec Serialization",  test_collection_instance_spec_serialization),
        ("CollectionSpec Serialization",          test_collection_spec_serialization),
        ("Dict Instances Rejected",               test_dict_instances_rejected),
        ("NoodleAttributes Composition",          test_noodle_attributes_composition),
    ]

    all_errors = []
    for name, fn in tests:
        try:
            errs = fn()
            if errs:
                all_errors.append((name, errs))
        except Exception as e:
            all_errors.append((name, [f"Test execution failed: {e}"]))

    return all_errors


def output_results(results):
    if results:
        sys.stdout.write("❌ Contract validation failures:\n")
        for name, errs in results:
            sys.stdout.write(f"\n{name}:\n")
            for e in errs:
                sys.stdout.write(f"  - {e}\n")
        return False
    sys.stdout.write("✅ All contract validation tests passed.\n")
    return True


if __name__ == "__main__":
    results = run_contract_validation_tests()
    success = output_results(results)
    sys.exit(0 if success else 1)
