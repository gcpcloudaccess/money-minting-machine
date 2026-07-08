from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ModelMetrics:
    accuracy: float
    precision: float
    recall: float
    baseline_accuracy: float
    samples: int


class StandardScaler:
    def __init__(self) -> None:
        self.means: list[float] = []
        self.stds: list[float] = []

    def fit(self, rows: list[list[float]]) -> None:
        width = len(rows[0])
        self.means = [sum(row[col] for row in rows) / len(rows) for col in range(width)]
        self.stds = []
        for col in range(width):
            variance = sum((row[col] - self.means[col]) ** 2 for row in rows) / len(rows)
            self.stds.append(math.sqrt(variance) or 1.0)

    def transform_one(self, row: list[float]) -> list[float]:
        return [(value - self.means[index]) / self.stds[index] for index, value in enumerate(row)]

    def transform(self, rows: list[list[float]]) -> list[list[float]]:
        return [self.transform_one(row) for row in rows]


class LogisticRegressionSGD:
    def __init__(self, learning_rate: float = 0.035, epochs: int = 160, l2: float = 0.003) -> None:
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.l2 = l2
        self.weights: list[float] = []
        self.bias = 0.0

    def fit(self, x_rows: list[list[float]], y: list[int]) -> None:
        if not x_rows:
            raise ValueError("Cannot train model without rows.")
        self.weights = [0.0] * len(x_rows[0])
        self.bias = 0.0

        positives = sum(y)
        negatives = len(y) - positives
        pos_weight = len(y) / (2.0 * positives) if positives else 1.0
        neg_weight = len(y) / (2.0 * negatives) if negatives else 1.0

        for _ in range(self.epochs):
            for features, label in zip(x_rows, y):
                probability = self.predict_proba_one(features)
                sample_weight = pos_weight if label == 1 else neg_weight
                error = (probability - label) * sample_weight
                for index, value in enumerate(features):
                    gradient = error * value + self.l2 * self.weights[index]
                    self.weights[index] -= self.learning_rate * gradient
                self.bias -= self.learning_rate * error

    def predict_proba_one(self, features: list[float]) -> float:
        score = self.bias + sum(weight * value for weight, value in zip(self.weights, features))
        if score >= 0:
            z = math.exp(-score)
            return 1.0 / (1.0 + z)
        z = math.exp(score)
        return z / (1.0 + z)


@dataclass
class TrainedModel:
    scaler: StandardScaler
    classifier: LogisticRegressionSGD
    metrics: ModelMetrics

    def predict_probability(self, features: list[float]) -> float:
        scaled = self.scaler.transform_one(features)
        return self.classifier.predict_proba_one(scaled)


def train_model(
    x_rows: list[list[float]],
    y: list[int],
    validation_fraction: float = 0.25,
) -> TrainedModel:
    if len(x_rows) < 60:
        raise ValueError("Need at least 60 labeled rows to train.")

    split = max(1, int(len(x_rows) * (1.0 - validation_fraction)))
    split = min(split, len(x_rows) - 1)
    train_x, valid_x = x_rows[:split], x_rows[split:]
    train_y, valid_y = y[:split], y[split:]

    scaler = StandardScaler()
    scaler.fit(train_x)
    scaled_train = scaler.transform(train_x)
    scaled_valid = scaler.transform(valid_x)

    classifier = LogisticRegressionSGD()
    classifier.fit(scaled_train, train_y)
    predictions = [1 if classifier.predict_proba_one(row) >= 0.5 else 0 for row in scaled_valid]
    metrics = _classification_metrics(valid_y, predictions)
    return TrainedModel(scaler=scaler, classifier=classifier, metrics=metrics)


def _classification_metrics(actual: list[int], predicted: list[int]) -> ModelMetrics:
    correct = sum(1 for truth, guess in zip(actual, predicted) if truth == guess)
    positives = sum(actual)
    baseline = max(positives, len(actual) - positives) / len(actual)
    true_positive = sum(1 for truth, guess in zip(actual, predicted) if truth == 1 and guess == 1)
    false_positive = sum(1 for truth, guess in zip(actual, predicted) if truth == 0 and guess == 1)
    false_negative = sum(1 for truth, guess in zip(actual, predicted) if truth == 1 and guess == 0)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    return ModelMetrics(
        accuracy=correct / len(actual),
        precision=precision,
        recall=recall,
        baseline_accuracy=baseline,
        samples=len(actual),
    )
