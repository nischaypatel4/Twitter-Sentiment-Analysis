# -*- coding: utf-8 -*-

!pip install stop-words pymorphy2

import pandas as pd
from string import punctuation
from stop_words import get_stop_words
from pymorphy2 import MorphAnalyzer
import re
import numpy as np
from sklearn.model_selection import train_test_split
from string import punctuation
from stop_words import get_stop_words
from pymorphy2 import MorphAnalyzer
import re
import spacy
from tqdm import tqdm
tqdm.pandas()
import nltk
from nltk.tokenize import word_tokenize
nltk.download("punkt")
from nltk.probability import FreqDist
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
import matplotlib.pyplot as plt

!pip install -q kaggle

from google.colab import files
files.upload()

!mkdir -p ~/.kaggle
!cp kaggle.json ~/.kaggle/
!chmod 600 ~/.kaggle/kaggle.json
!ls ~/.kaggle

!kaggle datasets list

!kaggle datasets download -d arkhoshghalb/twitter-sentiment-analysis-hatred-speech

!unzip twitter-sentiment-analysis-hatred-speech.zip

# !mkdir train
# !unzip train.zip -d train
df=pd.read_csv('/content/train.csv')
df_test=pd.read_csv('/content/test.csv')

df.head()

import seaborn as sns
sns.countplot(data=df, x='label')
plt.show()

label_counts = df['label'].value_counts()

plt.pie(label_counts, labels=label_counts.index, autopct='%1.1f%%', startangle=90)
plt.title('Label Distribution')
_ = plt.axis('equal')

df_train, df_val = train_test_split(df, test_size=0.3, shuffle=True, stratify=df['label'], random_state=42)

df_train.head()

sw = set(get_stop_words("en"))
puncts = set(punctuation)
morpher = MorphAnalyzer()


def preprocess_text(txt):
    txt = str(txt)
    txt = "".join(c for c in txt if c not in puncts)
    txt = txt.lower()
    txt = re.sub("not\s", "not", txt)
    txt = [morpher.parse(word)[0].normal_form for word in txt.split() if word not in sw]
    return " ".join(txt)

from tqdm import tqdm
tqdm.pandas()

df_train['tweet'] = df_train['tweet'].progress_apply(preprocess_text)
df_val['tweet'] = df_val['tweet'].progress_apply(preprocess_text)

train_corpus = " ".join(df_train["tweet"])
train_corpus = train_corpus.lower()

import nltk
from nltk.tokenize import word_tokenize
nltk.download("punkt")

tokens = word_tokenize(train_corpus)

max_words = 4000
max_len = 15
num_classes = 1
epochs = 6
batch_size = 512
print_batch_n = 100

tokens_filtered = [word for word in tokens if word.isalnum()]

from nltk.probability import FreqDist

dist = FreqDist(tokens_filtered)
tokens_filtered_top = [pair[0] for pair in dist.most_common(max_words-1)]

tokens_filtered_top[:15]

vocabulary = {v: k for k, v in dict(enumerate(tokens_filtered_top, 1)).items()}

import numpy as np


def text_to_sequence(text, maxlen):
    result = []
    tokens = word_tokenize(text.lower())
    tokens_filtered = [word for word in tokens if word.isalnum()]
    for word in tokens_filtered:
        if word in vocabulary:
            result.append(vocabulary[word])

    padding = [0] * (maxlen-len(result))
    return result[-maxlen:] + padding

x_train = np.asarray([text_to_sequence(text, max_len) for text in df_train["tweet"]], dtype=np.int32)
x_val = np.asarray([text_to_sequence(text, max_len) for text in df_val["tweet"]], dtype=np.int32)

x_train.shape

x_train[1]

from torch.utils.data import DataLoader, Dataset
import torch


class DataWrapper(Dataset):
    def __init__(self, data, target, transform=None):
        self.data = torch.from_numpy(data).long()
        self.target = torch.from_numpy(target).long()
        self.transform = transform

    def __getitem__(self, index):
        x = self.data[index]
        y = self.target[index]

        if self.transform:
            x = self.transform(x)

        return x, y

    def __len__(self):
        return len(self.data)

train_dataset = DataWrapper(x_train, df_train['label'].values)
train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

val_dataset = DataWrapper(x_val, df_val['label'].values)
val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=True)

from torch import nn


class RNNFixedLen(nn.Module) :
    def __init__(self, vocab_size, embedding_dim=128, hidden_dim=128, use_last=True):
        super().__init__()
        self.use_last = use_last
        self.embeddings = nn.Embedding(vocab_size, embedding_dim, padding_idx=0)
        self.rnn = nn.RNN(embedding_dim, hidden_dim, num_layers=2, batch_first=True, )
        self.linear = nn.Linear(hidden_dim, 1)
        self.dropout = nn.Dropout(0.2)

    def forward(self, x):
        x = self.embeddings(x)
        x = self.dropout(x)

        rnn_out, ht = self.rnn(x)
        if self.use_last:
          last_tensor = rnn_out[:,-1,:]
        else:
          last_tensor = torch.mean(rnn_out[:,:], dim=1)

        out = self.linear(last_tensor)
        return torch.sigmoid(out)

rnn_init = RNNFixedLen(max_words, 128, 20, use_last=False)
optimizer = torch.optim.Adam(rnn_init.parameters(), lr=0.001)
criterion = nn.BCELoss()

print(rnn_init)
print("Parameters:", sum([param.nelement() for param in rnn_init.parameters()]))

device = 'cuda' if torch.cuda.is_available() else 'cpu'
rnn_init.to(device)
device

rnn_init = rnn_init.to(device)
rnn_init.train()
th = 0.5

train_loss_history = []
test_loss_history = []


for epoch in range(epochs):
    rnn_init.train()
    running_items, running_right = 0.0, 0.0
    for i, data in enumerate(train_loader):
        inputs, labels = data[0].to(device), data[1].to(device)

        optimizer.zero_grad()
        outputs = rnn_init(inputs)
        loss = criterion(outputs, labels.float().view(-1, 1))
        loss.backward()
        optimizer.step()


        loss = loss.item()
        running_items += len(labels)

        pred_labels = torch.squeeze((outputs > th).int())
        running_right += (labels == pred_labels).sum()


    rnn_init.eval()

    print(f'Epoch [{epoch + 1}/{epochs}]. ' \
          f'Step [{i + 1}/{len(train_loader)}]. ' \
          f'Loss: {loss:.3f}. ' \
          f'Acc: {running_right / running_items:.3f}', end='. ')
    running_loss, running_items, running_right = 0.0, 0.0, 0.0
    train_loss_history.append(loss)

    test_running_right, test_running_total, test_loss = 0.0, 0.0, 0.0
    for j, data in enumerate(val_loader):
        test_labels = data[1].to(device)
        test_outputs = rnn_init(data[0].to(device))


        test_loss = criterion(test_outputs, test_labels.float().view(-1, 1))

        test_running_total += len(data[1])
        pred_test_labels = torch.squeeze((test_outputs > th).int())
        test_running_right += (test_labels == pred_test_labels).sum()

    test_loss_history.append(test_loss.item())
    print(f'Test loss: {test_loss:.3f}. Test acc: {test_running_right / test_running_total:.3f}')