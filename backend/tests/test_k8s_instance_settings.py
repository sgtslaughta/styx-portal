from app.config import Settings


def test_instance_setting_defaults():
    s = Settings()
    assert s.K8S_INSTANCE_NAMESPACE == "styx-instances"
    assert s.K8S_DESKTOP_IMAGE == "ghcr.io/sgtslaughta/styx-desktop:latest"
    assert s.INSTANCE_STORAGE_CLASS == "longhorn"
    assert s.INSTANCE_VOLUME_SIZE == "20Gi"
