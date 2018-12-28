import glob
import cv2
import numpy as np
import random
import pandas as pd
import math
from tqdm import tqdm_notebook as tqdm

import torch
import torch.utils.data
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torch.autograd as autograd
from torch.autograd import Variable
from torchvision import datasets, models, transforms

import sys
sys.path.append('../utils')
sys.path.append('../models')
from dataloaders import OneraPreloader, onera_siamese_loader
from metrics_and_losses import *
from unet_blocks import *

DROPOUT = 0.5

USE_CUDA = torch.cuda.is_available()

def w(v):
    if USE_CUDA:
        return v.cuda()
    return v

batch_size = 128
input_size = 32
bands = ['B02', 'B03', 'B04', 'B08']
data_dir = '../datasets/onera/'
weights_dir = '../weights/onera/'
train_csv = '../datasets/onera/train.csv'
test_csv = '../datasets/onera/test.csv'

def fit(epochs, verbose=False, layers=4, lr=0.001, init_filters=32, loss='dice', init_val=0.5):
    net = w(UNetClassify(layers=layers, init_filters=init_filters, init_val=init_val))
    criterion = get_loss(loss)
    optimizer = optim.Adam(net.parameters(), lr=lr)
    train_dataset = OneraPreloader(data_dir , train_csv, input_size, bands, onera_siamese_loader)
    train = torch.utils.data.DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=1)

    test_dataset = OneraPreloader(data_dir , test_csv, input_size, bands, onera_siamese_loader)
    test = torch.utils.data.DataLoader(test_dataset, batch_size=batch_size, shuffle=True, num_workers=1)

    best_iou = -1.0
    best_net_dict = None
    best_epoch = -1
    best_loss = 1000.0

    for epoch in tqdm(range(epochs)):
        net.train()
        train_losses = []
        for batch_img1, batch_img2, labels in train:
            batch_img1 = w(autograd.Variable(batch_img1))
            batch_img2 = w(autograd.Variable(batch_img2))
            labels = w(autograd.Variable(labels))

            optimizer.zero_grad()
            output = net(batch_img1, batch_img2)
            loss = criterion(output, labels.view(-1,1,32,32).float())
            loss.backward()
            train_losses.append(loss.item())

            optimizer.step()
        print('train loss', np.mean(train_losses))

        net.eval()
        losses = []
        iou = []
        to_show = random.randint(0, len(test) - 1)
        for batch_img1, batch_img2, labels_true in test:
            labels = w(autograd.Variable(labels_true))
            batch_img1 = w(autograd.Variable(batch_img1))
            batch_img2 = w(autograd.Variable(batch_img2))
            output = net(batch_img1, batch_img2)
            loss = criterion(output, labels.view(-1,1,32,32).float())
            losses += [loss.item()] * batch_size
            result = (F.sigmoid(output).data.cpu().numpy() > 0.5).astype(np.uint8)
            for label, res in zip(labels_true, result):
                label = label.cpu().numpy()[:, :]
#                 plt.imshow(label, cmap='tab20c')
#                 plt.show()
#                 plt.imshow(find_clusters(res), cmap='tab20c')
#                 plt.show()
                iou.append(evaluate_combined(label, find_clusters(res[0])))

        cur_iou = np.mean(iou)
        if cur_iou > best_iou or (cur_iou == best_iou and np.mean(losses) < best_loss):
            best_iou = cur_iou
            best_epoch = epoch
            import copy
            best_net_dict = copy.deepcopy(net.state_dict())
            best_loss = np.mean(losses)
        print(np.mean(losses), np.mean(iou), best_loss, best_iou)
    return best_iou, best_loss, best_epoch, best_net_dict


best_iou, best_loss, best_epoch, best_net_dict = fit(10)
torch.save(best_net_dict, '../weights/onera/unet_siamese_4band_2dates_dice.pt')
