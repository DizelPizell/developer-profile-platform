"""At most two screenshots are re-encoded at once (step 8.4): the third waits."""

import threading

from app.media import images


def test_third_reencode_waits_for_a_slot(monkeypatch):
    release = threading.Event()
    entered = []
    lock = threading.Lock()
    two_inside = threading.Event()

    def slow(data):
        with lock:
            entered.append(data)
            if len(entered) == 2:
                two_inside.set()
        release.wait(5)
        return data

    monkeypatch.setattr(images, "_reencode", slow)
    threads = [threading.Thread(target=images.reencode, args=(b"%d" % i,)) for i in range(3)]
    for thread in threads:
        thread.start()

    assert two_inside.wait(5)
    # Time for the third thread to enter, had nothing held it.
    threads[2].join(0.2)
    assert len(entered) == 2

    release.set()
    for thread in threads:
        thread.join(5)
    assert len(entered) == 3


def test_a_too_large_file_is_rejected_without_a_slot(monkeypatch):
    monkeypatch.setattr(images, "_reencode_slots", threading.BoundedSemaphore(1))
    images._reencode_slots.acquire()
    try:
        images.reencode(b"x" * (images.MAX_UPLOAD_BYTES + 1))
    except images.ImageRejected as exc:
        assert exc.kind == "image_too_large"
    else:
        raise AssertionError("expected ImageRejected")
