import os
import pathlib
import pickle
from typing import Dict, Tuple

import numpy as np

from sklearn.metrics import mean_squared_error
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import PolynomialFeatures
from sklearn.multioutput import MultiOutputRegressor
from sklearn import linear_model
from sklearn.preprocessing import StandardScaler
from natsort import natsorted

from tune_sklearn import TuneSearchCV
from tune_sklearn import TuneGridSearchCV
from sklearn.datasets import load_digits
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from sklearn.decomposition import PCA, NMF
from sklearn.feature_selection import SelectKBest, chi2
from sklearn.svm import SVR
from sklearn.pipeline import make_pipeline

from ray.tune.sklearn import TuneGridSearchCV, TuneSearchCV

from base import BaseModel
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# param_grid = {"learning_rate": (0.01, 0.1), "n_estimators": (25, 250), "subsample": [False, True]}


class SKModel(BaseModel):
    def build_model(self, model_type: str = "linear_model", scale_data: bool = False):
        self.scale_data = scale_data
        self.model_type = model_type
        if model_type == "linear_model":
            self.model = linear_model.LinearRegression()
        elif model_type == "SVR":
            self.model = make_pipeline(StandardScaler(), SVR(C=1.0, epsilon=0.2))
        elif model_type == "GradientBoostingRegressor":
            self.model = GradientBoostingRegressor()
        else:
            raise NotImplementedError("unknown model selected")

    def fit(self, X, y, fit_separate: bool = False):

        if self.scale_data:
            X, y = self.scalar(X, y)

        if self.model_type == "GradientBoostingRegressor" and fit_separate == False:
            fit_separate = True
            print(
                "Note: fit_separate should be True for GradientBoostingRegressor. Changing to True .."
            )

        if self.model_type == "SVR" and fit_separate == False:
            fit_separate = True
            print("Note: fit_separate should be True for SVR. Changing to True ..")

        self.separate_models = fit_separate

        if self.separate_models:
            self.models = []
            for i in range(y.shape[1]):
                logger.info(f"Fitting model {i+1} of {y.shape[1]}")
                self.models.append(self.model.fit(X, y[:, i]))
        else:
            try:
                self.model.fit(X, y)
            except ValueError:
                print(
                    f"fit separate should be True for model type of {self.model_type}"
                )

    def predict(self, X):

        if self.separate_models:
            pred = []
            if self.scale_data:
                X = self.xscalar.transform(X)
            for i in range(len(self.models)):
                logger.debug(f"Predicting model {i} of {len(self.models)}")
                pred.append(self.models[i].predict(X))

            preds = np.array(pred).transpose()
        else:
            preds = self.model.predict(X)
        if self.scale_data:
            preds = self.yscalar.inverse_transform(preds)

        # preds_df = pd.DataFrame(preds)
        # preds_df.columns = label_col_names
        return preds

    def save_model(self, filename):

        dir_path = pathlib.Path(filename).parent
        if not pathlib.Path(dir_path).exists():
            pathlib.Path(dir_path).mkdir(parents=True, exist_ok=True)
        if self.separate_models:
            # pickle.dump(self.models, open(filename, "wb"))
            if not pathlib.Path(filename).exists():
                pathlib.Path(filename).mkdir(parents=True, exist_ok=True)
            logger.info(f"Saving models to {filename}")
            for i in range(len(self.models)):
                save_path = os.path.join(filename, f"model{i}.pkl")
                logger.info(f"Saving model {i} to {save_path}")
                pickle.dump(self.models[i], open(save_path, "wb"))
        else:
            pickle.dump(self.model, open(filename, "wb"))

    def load_model(
        self, dir_path: str, scale_data: bool = False, separate_models: bool = False
    ):

        self.separate_models = separate_models
        if self.separate_models:
            all_models = os.listdir(dir_path)
            all_models = natsorted(all_models)
            num_models = len(all_models)
            models = []
            for i in range(num_models):
                models.append(
                    pickle.load(open(os.path.join(dir_path, all_models[i]), "rb"))
                )
            self.models = models
        else:
            self.model = pickle.load(open(dir_path, "rb"))

        self.scale_data = scale_data

    def sweep(self, X, y, params: Dict = None):
        if not params:
            raise NotImplementedError

        tune_search = TuneSearchCV(
            self.model,
            param_distributions=params,
            n_trials=3,
            # early_stopping=True,
            # use_gpu=True
        )

        tune_search.fit(X, y)

        return tune_search


if __name__ == "__main__":

    """Example using an sklearn Pipeline with TuneGridSearchCV.

    Example taken and modified from
    https://scikit-learn.org/stable/auto_examples/compose/
    plot_compare_reduction.html
    """

    skm = SKModel()
    X, y = skm.load_csv(
        dataset_path="csv_data/cartpole-log.csv",
        max_rows=1000,
        augm_cols=["action_command", "config_length", "config_masspole"],
    )

    skm.build_model(model_type="linear_model")
    skm.fit(X, y, fit_separate=False)
    print(X)
    yhat = skm.predict(X)

    skm.save_model(dir_path="models/linear_pole_multi.pkl")

    skm = SKModel()
    X, y = skm.load_csv(
        dataset_path="csv_data/cartpole-log.csv",
        max_rows=1000,
        augm_cols=["action_command", "config_length", "config_masspole"],
    )

    skm.build_model(model_type="SVR")
    skm.fit(X, y, fit_separate=False)
    print(X)
    yhat = skm.predict(X)

    skm.save_model(dir_path="models/lsvc_pole_multi.pkl")

    skm.build_model(model_type="GradientBoostingRegressor")
    skm.fit(X, y, fit_separate=False)
    print(X)
    yhat = skm.predict(X)

    skm.save_model(dir_path="models/gbr_pole_multi.pkl")

    # from sklearn.model_selection import GridSearchCV
    # from sklearn.datasets import load_digits
    # from sklearn.pipeline import Pipeline
    # from sklearn.svm import LinearSVC
    # from sklearn.decomposition import PCA, NMF
    # from sklearn.feature_selection import SelectKBest, chi2

    # from tune_sklearn import TuneSearchCV
    # from tune_sklearn import TuneGridSearchCV

    # pipe = Pipeline(
    #     [
    #         # the reduce_dim stage is populated by the param_grid
    #         ("reduce_dim", "passthrough"),
    #         ("classify", LinearSVC(dual=False, max_iter=10000)),
    #     ]
    # )

    # N_FEATURES_OPTIONS = [2, 4, 8]
    # C_OPTIONS = [1, 10]
    # param_grid = [
    #     {
    #         "reduce_dim": [PCA(iterated_power=7), NMF()],
    #         "reduce_dim__n_components": N_FEATURES_OPTIONS,
    #         "classify__C": C_OPTIONS,
    #     },
    #     {
    #         "reduce_dim": [SelectKBest(chi2)],
    #         "reduce_dim__k": N_FEATURES_OPTIONS,
    #         "classify__C": C_OPTIONS,
    #     },
    # ]

    # random = TuneSearchCV(pipe, param_grid, search_optimization="random")
    # X, y = load_digits(return_X_y=True)
    # random.fit(X, y)
    # print(random.cv_results_)

    # grid = TuneGridSearchCV(pipe, param_grid=param_grid)
    # grid.fit(X, y)
    # print(grid.cv_results_)

