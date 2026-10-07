"""
Extract a portable sklearn pipeline from a trained AutoGluon predictor.

The output pipeline takes raw input features (post-Snowflake-table column-name standardization)
and produces predictions, with NO autogluon dependency at inference. AG's feature steps
(AsType / FillNa / Identity / CategoryFeatureGenerator / DropUnique / DropDuplicates) are
translated to sklearn equivalents (SimpleImputer / OrdinalEncoder / OneHotEncoder), reusing
AG's already-fitted state where possible.

For classification, the caller must pass `classifier_wrapper=<class defined in __main__>` so
cloudpickle inlines the class by value when registering on Snowflake. (Snowflake's registry
treats unknown modules as missing conda packages and rejects the model otherwise.) A reference
implementation is in this module's docstring — copy it into your registration script:

    from sklearn.base import BaseEstimator, ClassifierMixin
    from sklearn.preprocessing import LabelEncoder

    class LabelEncodedClassifier(BaseEstimator, ClassifierMixin):
        '''XGBoost requires int labels; AG handles strings via its label cleaner.
        Wrap so the portable pipeline accepts/returns raw string targets.'''
        def __init__(self, estimator):
            self.estimator = estimator
        def fit(self, X, y):
            self.le_ = LabelEncoder()
            self.estimator.fit(X, self.le_.fit_transform(y))
            self.classes_ = self.le_.classes_
            return self
        def predict(self, X):
            return self.le_.inverse_transform(self.estimator.predict(X).astype(int))
        def predict_proba(self, X):
            return self.estimator.predict_proba(X)

Use for Option A registration (warehouse inference, scikit-learn framework). Ensembles,
forecasting, and clustering must use Option B (CustomModel).

Verified against autogluon==1.5.1b20260415 on tabular tree models (LightGBM, XGBoost, CatBoost).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


def _split_columns_by_role(X_train, predictor):
    """Split columns into numeric vs categorical using raw training data dtypes.

    AG's feature_metadata.type_map_raw describes the *output* of feature_generator
    (binary-encoded sex=int8, label-encoded categoricals), not the *input* — we need
    input dtypes for the sklearn ColumnTransformer to fit on raw data.
    """
    numeric = X_train.select_dtypes(include=["number"]).columns.tolist()
    categorical = [c for c in X_train.columns if c not in numeric]
    cat_levels = {}
    fg = predictor._learner.feature_generator
    for sub in fg.generators:
        for g in (sub if isinstance(sub, list) else [sub]):
            cm = getattr(g, "category_map", None)
            if cm:
                for col, levels in cm.items():
                    if col in categorical:
                        cat_levels[col] = list(levels)
    return numeric, categorical, cat_levels


def _build_feature_transformer(predictor, X_train):
    """Build a sklearn ColumnTransformer mirroring AG's feature pipeline.

    Numerics: median-impute. Categoricals: most-frequent-impute + OneHotEncoder.
    Categorical levels are pulled from AG's CategoryFeatureGenerator.category_map when
    available, so test-time encoding matches training-time encoding for unseen values.
    """
    numeric, categorical, cat_levels = _split_columns_by_role(X_train, predictor)

    onehot_kwargs = dict(handle_unknown="ignore", sparse_output=False)
    if categorical and all(c in cat_levels for c in categorical):
        onehot_kwargs["categories"] = [cat_levels[c] for c in categorical]

    transformers = []
    if numeric:
        transformers.append((
            "num",
            Pipeline([("impute", SimpleImputer(strategy="median"))]),
            numeric,
        ))
    if categorical:
        transformers.append((
            "cat",
            Pipeline([
                ("impute", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(**onehot_kwargs)),
            ]),
            categorical,
        ))
    return ColumnTransformer(transformers, remainder="drop", sparse_threshold=0.0)


def extract_portable_pipeline(predictor, model_name, X_train, y_train,
                              classifier_wrapper=None, pre_transformer=None):
    """
    Build a portable sklearn Pipeline equivalent to predictor's selected model.

    Steps:
        1. Translate AG's feature_generator + wrapper.preprocess to a sklearn ColumnTransformer.
        2. Refit the native estimator (LGBMClassifier / XGBClassifier / CatBoostClassifier /
           respective regressors) on the new transformed matrix, reusing AG's hyperparameters.

    For classification, pass `classifier_wrapper=<class>` (defined in __main__ of the
    registration script) — see module docstring for the reference LabelEncodedClassifier.

    For Snowflake warehouse inference, pass `pre_transformer=FunctionTransformer(<func>,
    validate=False)` where <func> is a __main__-defined function that coerces pandas
    nullable dtypes (pd.NA) to numpy-compatible (np.nan). Without this, SimpleImputer's
    mask logic raises "boolean value of NA is ambiguous" on warehouse-side inference.

    Returns a fitted Pipeline. No autogluon imports needed at inference.
    """
    model = predictor._trainer.load_model(model_name)
    if hasattr(model, "load_child") and getattr(model, "models", None):
        wrapper = model.load_child(model.models[0])
    else:
        wrapper = model
    underlying = wrapper.model
    family = type(underlying).__module__
    is_clf = predictor.problem_type in ("binary", "multiclass")

    if "lightgbm" in family:
        from lightgbm import LGBMClassifier, LGBMRegressor
        sk_params = {
            k: v for k, v in underlying.params.items()
            if k not in ("objective", "metric", "verbose", "num_classes", "num_class")
        }
        native_cls = LGBMClassifier if is_clf else LGBMRegressor
    elif "xgboost" in family:
        sk_params = underlying.get_xgb_params()
        from xgboost import XGBClassifier, XGBRegressor
        native_cls = XGBClassifier if is_clf else XGBRegressor
    elif "catboost" in family:
        import inspect
        from catboost import CatBoostClassifier, CatBoostRegressor
        native_cls = CatBoostClassifier if is_clf else CatBoostRegressor
        valid = set(inspect.signature(native_cls.__init__).parameters)
        EVAL_SET_DEPS = {"use_best_model", "od_type", "od_wait", "od_pval"}
        sk_params = {
            k: v for k, v in underlying.get_all_params().items()
            if k in valid and k not in EVAL_SET_DEPS
        }
    else:
        raise NotImplementedError(
            f"Portable extraction for {family!r} not implemented. Use Option B (CustomModel)."
        )

    feature_step = _build_feature_transformer(predictor, X_train)
    estimator = native_cls(**sk_params)
    if is_clf and classifier_wrapper is not None:
        estimator = classifier_wrapper(estimator)
    steps = []
    if pre_transformer is not None:
        steps.append(("pre", pre_transformer))
    steps.append(("features", feature_step))
    steps.append(("model", estimator))
    pipe = Pipeline(steps)
    pipe.fit(X_train, y_train)
    return pipe
