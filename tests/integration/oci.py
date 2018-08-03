import hashlib
import json
import os
import pytest
import tarfile

from tests.testutils import cli_integration as cli
from tests.testutils.integration import assert_contains


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


# Test that a oci build 'works'
@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
def test_oci_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'oci/ocihello.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['checkout', element_name, checkout])
    assert result.exit_code == 0

    # Verify basic directory structure
    assert_contains(checkout, ['/oci-layout', '/index.json', '/blobs'])

    # Verify that we have at least one manifest
    with open(os.path.join(checkout, 'index.json')) as f:
        index = json.load(f)
    manifests = [x for x in index['manifests']
                 if x['mediaType'] == 'application/vnd.oci.image.manifest.v1+json']
    assert len(manifests) > 0

    # Now verify that the manifests are valid
    blobs_dir = os.path.join(checkout, 'blobs')
    all_layers = []
    all_diff_ids = []
    for manifest in manifests:
        layers, diff_ids = extract_layers(manifest, blobs_dir)
        all_layers += layers
        all_diff_ids += diff_ids
    assert len(all_layers) == len(all_diff_ids)

    # Finally, extract all layers and ensure that only the desired file are
    # present
    extract_dir = os.path.join(cli.directory, 'extract')
    for layer in all_layers:
        with tarfile.open(layer) as f:
            f.extractall(path=extract_dir)

    assert_contains(extract_dir, ['/subdir', '/subdir/test.txt', '/test.txt'])


# Extract layers from given manifest and verify manifests in the process
def extract_layers(short_manifest, blobs_dir):
    manifest_path = get_blob(short_manifest['digest'], short_manifest['size'], blobs_dir)

    with open(manifest_path) as f:
        manifest = json.load(f)

    # Assert we have both 'config' and 'layers' sections
    assert 'config' in manifest
    assert 'layers' in manifest

    # Verify basic layout
    assert manifest['config']['mediaType'] == 'application/vnd.oci.image.config.v1+json'
    assert len(manifest['layers']) > 0
    for layer in manifest['layers']:
        assert layer['mediaType'] == 'application/vnd.oci.image.layer.v1.tar+gzip'

    config_path = get_blob(manifest['config']['digest'],
                           manifest['config']['size'], blobs_dir)
    layers_path = [get_blob(layer['digest'], layer['size'], blobs_dir)
                   for layer in manifest['layers']]

    with open(config_path) as f:
        config = json.load(f)

    assert len(config['rootfs']['diff_ids']) == len(manifest['layers'])
    return layers_path, config['rootfs']['diff_ids']


# Get path to the blob pointed by given digest
def get_blob(digest_str, size, blobs_dir):
    algorigthm, digest = digest_str.strip().split(':')
    # We only support sha256 at present
    assert algorigthm == 'sha256'

    # Verify that our digest points to a vaild blob and that its attributes
    # match what we were given
    blob_path = os.path.join(blobs_dir, algorigthm, digest)
    assert os.path.isfile(blob_path)
    assert os.path.getsize(blob_path) == size
    with open(blob_path, 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == digest

    return blob_path
