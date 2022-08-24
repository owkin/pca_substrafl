import numpy as np
import substratools as tools
from sklearn.metrics import roc_auc_score


class AUC(tools.Metrics):
    def score(self, inputs, outputs):
        """AUC"""

        y_pred = self.get_predictions(inputs["predictions"])
        y_true = inputs["y"]

        metric = roc_auc_score(y_true, y_pred) if len(set(y_true)) > 1 else 0

        tools.save_performance(float(metric), outputs["performance"])

    def get_predictions(self, path):
        return np.load(path)


if __name__ == "__main__":
    tools.metrics.execute(AUC())
