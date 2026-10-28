
from ultralytics import YOLO


class VehicleDetector:
    def __init__(
        self,
        model_path="models/yolov8n.pt",
        confidence=0.30,
        image_size=640,
    ):
        self.model = YOLO(model_path)
        self.confidence = confidence
        self.image_size = image_size

        # COCO class IDs
        self.vehicle_classes = [0, 2, 3, 5, 7]

    def detect(self, frame):
        results = self.model.predict(
            source=frame,
            conf=self.confidence,
            imgsz=self.image_size,
            classes=self.vehicle_classes,
            verbose=False,
        )

        result = results[0]
        annotated_frame = result.plot()

        counts = {
            "car": 0,
            "motorcycle": 0,
            "bus": 0,
            "truck": 0,
            "person": 0,

        }

        if result.boxes is not None:
            for class_id in result.boxes.cls.int().tolist():
                class_name = self.model.names[class_id]

                if class_name in counts:
                    counts[class_name] += 1

        return annotated_frame, counts
