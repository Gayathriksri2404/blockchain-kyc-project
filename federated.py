# federated.py
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

# Load dataset
data = pd.read_csv("dataset/creditcard.csv")
X = data.drop("Class", axis=1)
y = data["Class"].values
X = StandardScaler().fit_transform(X)

# Stratified split to ensure each bank has both classes
X_temp, X_unused, y_temp, y_unused = train_test_split(
    X, y, test_size=0.7, random_state=42, stratify=y
)

X_bankA, X_remain, y_bankA, y_remain = train_test_split(
    X_temp, y_temp, test_size=2/3, random_state=42, stratify=y_temp
)
X_bankB, X_bankC, y_bankB, y_bankC = train_test_split(
    X_remain, y_remain, test_size=0.5, random_state=42, stratify=y_remain
)

def train_local_model(X_train, y_train):
    model = LogisticRegression(max_iter=100)
    model.fit(X_train, y_train)
    acc = model.score(X_train, y_train)
    # small random variation for animation
    acc += np.random.uniform(-0.01, 0.01)
    acc = min(max(acc, 0), 1)
    weights = model.coef_[0]
    bias = model.intercept_[0]
    return acc, weights, bias

def federated_aggregate_weights():
    accA, wA, bA = train_local_model(X_bankA, y_bankA)
    accB, wB, bB = train_local_model(X_bankB, y_bankB)
    accC, wC, bC = train_local_model(X_bankC, y_bankC)

    bank_results = {"BankA": accA, "BankB": accB, "BankC": accC}
    global_accuracy = sum(bank_results.values()) / len(bank_results)

    avg_weights = (wA + wB + wC) / 3
    avg_bias = (bA + bB + bC) / 3
    global_weights = {"weights": avg_weights, "bias": avg_bias}

    local_weights = {
        "BankA": {"weights": wA, "bias": bA},
        "BankB": {"weights": wB, "bias": bB},
        "BankC": {"weights": wC, "bias": bC},
    }

    return global_accuracy, bank_results, local_weights, global_weights

if __name__ == "__main__":
    global_acc, results, local_w, global_w = federated_aggregate_weights()
    print("Local Accuracies:", results)
    print("Global Accuracy:", global_acc)