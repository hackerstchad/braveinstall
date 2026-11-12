import braveinstall


def test_version():
    assert braveinstall.APP_VERSION == "2.0.0"


def test_constants():
    assert braveinstall.APP_NAME == "BraveInstall"
    assert braveinstall.EXIT_SUCCESS == 0
    assert braveinstall.EXIT_ERROR == 1
