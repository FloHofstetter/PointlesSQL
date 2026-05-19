# %% [markdown]
# # ML quickstart
#
# Pull features, train a tiny scikit-learn model, log to MLflow.
# Replace the feature query before running.

# %%
from pointlessql.pql import PQL

# %%
# %sql -o features SELECT * FROM main.public.training_features LIMIT 1000

# %%
features.describe()

# %%
# from sklearn.linear_model import LogisticRegression
# import mlflow
# X = features.drop(columns=["label"])
# y = features["label"]
# model = LogisticRegression().fit(X, y)
# mlflow.sklearn.log_model(model, "model")
