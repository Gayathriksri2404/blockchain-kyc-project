# 🔹 Simulated local fraud detection accuracy for each bank
def local_training(bank_name):
    scores = {
        "BankA": 0.72,
        "BankB": 0.80,
        "BankC": 0.77
    }
    return scores.get(bank_name, 0.75)


# 🔹 Federated aggregation (average of all banks)
def federated_aggregate():
    banks = ["BankA", "BankB", "BankC"]

    total = 0
    results = {}

    for bank in banks:
        score = local_training(bank)
        results[bank] = score
        total += score

    global_model = total / len(banks)

    return global_model, results