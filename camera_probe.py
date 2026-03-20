import cv2
from pygrabber.dshow_graph import FilterGraph


BACKENDS = [
    ("default", None),
    ("any", cv2.CAP_ANY),
    ("msmf", cv2.CAP_MSMF),
    ("dshow", cv2.CAP_DSHOW),
]


def main():
    print("DirectShow device names:", FilterGraph().get_input_devices())
    for index in range(4):
        print(f"\n=== camera index {index} ===")
        for name, backend in BACKENDS:
            try:
                if backend is None:
                    cap = cv2.VideoCapture(index)
                else:
                    cap = cv2.VideoCapture(index, backend)
            except Exception as exc:
                print(f"{name:8} open failed: {exc}")
                continue

            if not cap.isOpened():
                print(f"{name:8} not opened")
                cap.release()
                continue

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, 60)
            ret, frame = cap.read()
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            print(f"{name:8} opened ret={ret} size={width}x{height} fps={fps:.2f} frame={'ok' if ret else 'ng'}")
            if ret and frame is not None:
                cv2.putText(
                    frame,
                    f"index={index} backend={name} size={width}x{height}",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (0, 255, 0),
                    2,
                )
                cv2.imshow(f"probe-{index}-{name}", frame)
                cv2.waitKey(1200)
                cv2.destroyWindow(f"probe-{index}-{name}")
            cap.release()

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
