#!/usr/bin/env python3
"""
models.py - 模型定义 (PyTorch)

支持的模型:
  - MLP: 多层感知机
  - RNN: 简单循环神经网络
  - LSTM: 长短期记忆网络
"""

import torch
import torch.nn as nn


class MLP(nn.Module):
    """多层感知机"""

    def __init__(self, input_size, num_classes=3, hidden_layers=[512, 256, 128, 64],
                 dropout_rate=0.3):
        super(MLP, self).__init__()

        layers = []
        in_features = input_size

        for hidden_size in hidden_layers:
            layers.append(nn.Linear(in_features, hidden_size))
            layers.append(nn.BatchNorm1d(hidden_size))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(dropout_rate))
            in_features = hidden_size

        layers.append(nn.Linear(in_features, num_classes))

        self.model = nn.Sequential(*layers)

    def forward(self, x):
        return self.model(x)


class RNNClassifier(nn.Module):
    """RNN分类器"""

    def __init__(self, input_size, num_classes=3, rnn_units=[128, 64],
                 dropout_rate=0.3):
        super(RNNClassifier, self).__init__()

        # 两层堆叠RNN
        self.rnn = nn.RNN(
            input_size=input_size,
            hidden_size=rnn_units[0],
            num_layers=2,
            batch_first=True,
            dropout=dropout_rate
        )

        self.fc = nn.Sequential(
            nn.BatchNorm1d(rnn_units[0]),
            nn.Dropout(dropout_rate),
            nn.Linear(rnn_units[0], 64),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Dropout(dropout_rate / 2),
            nn.Linear(32, num_classes)
        )

    def forward(self, x):
        # x: (batch, seq_len, features)
        out, _ = self.rnn(x)
        out = out[:, -1, :]  # 取最后时间步
        out = self.fc(out)
        return out


class LSTMClassifier(nn.Module):
    """LSTM分类器"""

    def __init__(self, input_size, num_classes=3, lstm_units=[128, 64],
                 dropout_rate=0.3):
        super(LSTMClassifier, self).__init__()

        # 两层堆叠LSTM
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=lstm_units[0],
            num_layers=2,
            batch_first=True,
            dropout=dropout_rate
        )

        self.fc = nn.Sequential(
            nn.BatchNorm1d(lstm_units[0]),
            nn.Dropout(dropout_rate),
            nn.Linear(lstm_units[0], 64),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Dropout(dropout_rate / 2),
            nn.Linear(32, num_classes)
        )

    def forward(self, x):
        # x: (batch, seq_len, features)
        out, _ = self.lstm(x)
        out = out[:, -1, :]  # 取最后时间步
        out = self.fc(out)
        return out


# 模型注册表
MODEL_REGISTRY = {
    'mlp': MLP,
    'rnn': RNNClassifier,
    'lstm': LSTMClassifier,
}


def get_model(model_name, input_shape, num_classes=3, **kwargs):
    """
    获取模型

    参数:
        model_name: 模型名称 ('mlp', 'rnn', 'lstm')
        input_shape: 输入形状
            - MLP: (flattened_features,)
            - RNN/LSTM: (seq_len, features)
        num_classes: 分类数量
        **kwargs: 模型特定参数

    返回:
        model: PyTorch模型
    """
    if model_name not in MODEL_REGISTRY:
        raise ValueError(f"Unknown model: {model_name}. Available: {list(MODEL_REGISTRY.keys())}")

    if model_name == 'mlp':
        input_size = input_shape[0]
    else:
        input_size = input_shape[1]  # features维度

    return MODEL_REGISTRY[model_name](input_size, num_classes, **kwargs)
