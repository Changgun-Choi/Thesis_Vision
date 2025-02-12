# -*- coding: utf-8 -*-
"""
Created on Tue Dec 28 20:21:04 2021

@author: ChangGun Choi
https://wikidocs.net/book/1 Python
https://wikidocs.net/52460 Pytorch
https://yhkim4504.tistory.com/5?category=843360
https://hongl.tistory.com/235



"""
#%%
import torch
import torch.nn as nn
import torchvision
import torch.nn.functional as F
import matplotlib.pyplot as plt
#%matplotlw32ew3ib inline

from torch import optim
from torchvision import datasets
import torchvision.transforms as transforms
from torch.utils.data import DataLoader
import os
from torchvision import utils
from torchvision.datasets import CIFAR10

from torch import nn
from torch import Tensor
from PIL import Image
from torchvision.transforms import Compose, Resize, ToTensor
from einops import rearrange, reduce, repeat
from einops.layers.torch import Rearrange, Reduce
from torchsummary import summary
import numpy as np
import time
import copy
import random
from tqdm import tqdm
import math

# Device configuration
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

import ssl
ssl._create_default_https_context = ssl._create_unverified_context

#!pip3 install ipywidgets --user

#%%
# specify path to data
path2data = 'C:/Users/ChangGun Choi/Team Project/Thesis_Vision/data'

# if not exists the path, make the directory
if not os.path.exists(path2data):
    os.mkdir(path2data)

# load dataset
#train_ds = datasets.STL10(path2data, split='train', download=True, transform=transforms.ToTensor())
#val_ds = datasets.STL10(path2data, split='test', download=True, transform=transforms.ToTensor())
transform = transforms.Compose(
    [transforms.ToTensor(),
     transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])

batch_size = 4

train_ds = torchvision.datasets.CIFAR10(root=path2data, train=True,download=True, transform=transform)
train_dl  = torch.utils.data.DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=2)

val_ds = torchvision.datasets.CIFAR10(root=path2data, train=False, download=True, transform=transform)
val_dl  = torch.utils.data.DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=2)

classes = ('plane', 'car', 'bird', 'cat',
           'deer', 'dog', 'frog', 'horse', 'ship', 'truck')

#%%

def show(img, y=None):
    npimg = img.numpy()
    npimg_tr = np.transpose(npimg, (1, 2, 0))
    plt.imshow(npimg_tr)

    if y is not None:
        plt.title('labels:' + str(y))

np.random.seed(10)
torch.manual_seed(0)

grid_size=4
rnd_index = np.random.randint(0, len(train_ds), grid_size) # 4 grid
rnd_index   # array([40059,  9372, 10201, 37597])
train_ds[40059][1]
#%%
x_grid = [train_ds[i][0] for i in rnd_index]  # i 는 random index
y_grid = [train_ds[i][1] for i in rnd_index]
x_grid
y_grid
x_grid = torchvision.utils.make_grid(x_grid, nrow=grid_size, padding=2)
plt.figure(figsize=(10,10))
show(x_grid, y_grid)

#%%
"1. PatchEmbedding"
#latent vector 사이즈 D 를 모든 레이어에 걸쳐 사용하는데, 이를 통해 패치들을 flatten 시키고 D차원으로 매핑
#https://hongl.tistory.com/235 ,  https://yhkim4504.tistory.com/5

#To handle 2D images, reshape the image into a sequence of flattened 2D patches.
class PatchEmbedding(nn.Module):
    def __init__(self, in_channels=3, patch_size=16, emb_size=768, img_size=256):
        super().__init__()
        self.patch_size = patch_size # 패치 이미지의 가로,세로 길이
        self.patch_num = img_size // patch_size # patch_num**2 이 전체 갯수
        
        " Method 1: Flatten and FC  "
        # self.projection = nn.Sequential(
        #     Rearrange('b c (h s1) (w s2) -> b (h w) (s1 s2 c)', s1=patch_size, s2=patch_size),
        #     nn.Linear(path_size * patch_size * in_channels, emb_size))  
        " path_size * patch_size * in_channels : patch_vec_size "

        # Method 2: Conv (1차원 Flatten)
        #패치 임베딩 projection 는 CNN feature map으로부터 뽑아낸 패치들에 적용
        #input sequence가 feature map의 spatial dimension을 flatten 시키고 트랜스포머 차원으로 projecting 시킴으로써 나온 것
        self.projection = nn.Sequential(
            
            # using a conv layer instead of a linear one -> performance gains
            nn.Conv2d(in_channels, emb_size, patch_size, stride=patch_size),
            Rearrange('b e (h) (w) -> b (h w) e')
        )
                         # 학습가능 embedding
        self.cls_token = nn.Parameter(torch.randn(1,1,emb_size)) # BERT cls토큰 #(1, 1, 768)
        self.positions = nn.Parameter(torch.randn((self.patch_num)**2 + 1, emb_size))
                                                # 패치 갯수 + cls토큰 만큼 position 만듬
    def forward(self, x):
        batch_size = x.shape[0]
        x = self.projection(x)
        # cls_token을 반복하여 배치사이즈의 크기와 맞춰줌
        cls_tokens = repeat(self.cls_token, '() n e -> b n e', b=batch_size) #(16, 1, 768)
        # cls_token과 projected_x를 concatenate
        x = torch.cat([cls_tokens, x], dim=1)  # 196 + 1 = 197 # dim=1은 가로 row로 붙이는 것: dimension이 늘어나야하거는 니까
        # add position embedding to prejected patches
        x += self.positions  # 자동으로 크기를 맞춰서 연산을 수행하게 만듬: Broadcasting
        
        return x   
#%%
# x를 패치로 나누고 flatten시키면 (8, 196, 768)의 텐서가 됩니다. 그 후 cls_token을 맨 앞에 붙여서 (8, 197, 768)의 텐서로 만들기 위해
# cls_token을 (1, 1, 768)의 파라미터로 생성해줍니다. 생성된 파라미터는 einops의 repeat을 이용하여 (8, 1, 768) 사이즈로 확장됩니다. 이후 torch.cat을 통하여 dim=1인 차원에 concatenate시켜줍니다.
# Position Encoding은 cls_token으로 늘어난 크기에 맞춰 1을 더한 (197, 768) 사이즈로 생성후 마지막에 더해주면 됩니다. 브로드캐스팅된 + 연산은 모든 배치에 같은 Pos Encoding을 더하게 됩니다.

# Testing
in_channels=3
patch_size=16  # x(input 개수)
emb_size=768
img_size=256
x = torch.randn(16, 3, 224, 224).to(device) # batchsize: 16

projection = nn.Sequential(
    # using a conv layer instead of a linear one -> performance gains
    nn.Conv2d(in_channels, emb_size, patch_size, stride=patch_size), # filter가 patchsize
    Rearrange('b e (h) (w) -> b (h w) e') # e: dimension             # 안겹치게 stride
).to(device)

cls_token = nn.Parameter(torch.randn(1,1,emb_size)).to(device)
positions = nn.Parameter(torch.randn((img_size // patch_size) * (img_size // patch_size) + 1, emb_size)).to(device)
batch_size = 16
cls_tokens = repeat(cls_token, '() n e -> b n e', b=batch_size)

print(projection(x).size()) #torch.Size([16, 196, 768])  # 패치갯수: 14 * 14 = 196
print(cls_token.size())  #torch.Size([1, 1, 768])  # 랜덤이여서 배워야하는 parameter
print(cls_tokens.shape)  #torch.Size([16, 1, 768])
print(positions.size())  #torch.Size([197, 768])   # 배워야하는 parameter

patch_embedding = PatchEmbedding().to(device)
patch_output = patch_embedding(x)
print('[batch, 1+num of patches, emb_size] = ', patch_output.shape) # torch.Size([16, 197, 768])

#%% 
"2. Multi-Head: 각 Linear Projection을 거친 QKV를 rearrange를 통해 8개의 Multi-Head로 나눠주게 됩니다"

emb_size = 768
num_heads = 8
#입력텐서는 3개의 Linear Projection
keys = nn.Linear(emb_size, emb_size).to(device)
queries = nn.Linear(emb_size, emb_size).to(device)
values = nn.Linear(emb_size, emb_size).to(device)
print(keys, queries, values)

x = patch_output
"각 head마다 임베딩차원으로 나눔 [batch, head, 1+num of patches, emb/head]"
queries = rearrange(queries(x), "b n (h d) -> b h n d", h=num_heads)
keys = rearrange(keys(x), "b n (h d) -> b h n d", h=num_heads)
values  = rearrange(values(x), "b n (h d) -> b h n d", h=num_heads)
#torch.Size([16, 8, 197, 96]) # batch, head, patch + 1, 768/8 (8개 head로 나눔)
print('shape :', queries.shape, keys.shape, values.shape)

# Scale Dot product
# Queries * Key         
energy = torch.einsum('bhqd, bhkd -> bhqk', queries, keys)
print('energy :', energy.shape) #torch.Size([16, 8, 197, 197])

def forward(self, x : Tensor, mask: Tensor = None):
    if mask is not None:
        fill_value = torch.finfo(torch.float32).min  
        energy.mask_fill(~mask, fill_value)
fill_value = torch.finfo(torch.float32).min
fill_value
energy

# Get Attention Score
scaling = emb_size ** (1/2) # 분수
att = F.softmax(energy, dim=-1) / scaling  # Attention score
print('att :', att.shape) #att : torch.Size([16, 8, 197, 197])

# Attention Score * values
out = torch.einsum('bhal, bhlv -> bhav ', att, values)
print('out :', out.shape) #out : torch.Size([16, 8, 197, 96])

# Rearrage to emb_size
out = rearrange(out, "b h n d -> b n (h d)")
print('out2 : ', out.shape) #out2 :  torch.Size([16, 197, 768]) # 8 heads 더해짐

#%%
class MultiHeadAttention(nn.Module):
    def __init__(self, emb_size: int = 768, num_heads: int = 8, dropout: float = 0):
        super().__init__()
        self.emb_size = emb_size
        self.num_heads = num_heads
        # fuse the queries, keys and values in one matrix
        self.qkv = nn.Linear(emb_size, emb_size * 3) # 더해짐
        self.att_drop = nn.Dropout(dropout)
        self.projection = nn.Linear(emb_size, emb_size)
        
    def forward(self, x : Tensor, mask: Tensor = None): 
        #선택적 인수에 기본값 None을 제공 한 다음 해당 값이 None인지 테스트하여 지정되었는지 확인하는 것입니다
        # split keys, queries and values in num_heads
        qkv = rearrange(self.qkv(x), "b n (h d qkv) -> (qkv) b h n d", h=self.num_heads, qkv=3)
        queries, keys, values = qkv[0], qkv[1], qkv[2] # qkv 3개니까
        # sum up over the last axis
        energy = torch.einsum('bhqd, bhkd -> bhqk', queries, keys) # batch, num_heads, query_len, key_len
        
        # Maksing option: 빈 token을 pad token 
        # mask matrix에서 pad token에 해당하는 row, column의 모든 값은 −inf이다. 그 외에는 모두 1이다.
        #(seq_len×seq_len) shape의 mask matrix를 곱하는 방식
        #pad mask matrix는 Transformer 외부 (대개 Batch class)에서 생성되어 Transformer에 인자로 들어오게 된다
        if mask is not None: # 기본값이 None 인 변수일떄
            fill_value = torch.finfo(torch.float32).min # 실수중에 최소 # maks가 1이면 mask 안한다는 뜻(그대로 attention사용)
            energy.mask_fill(~mask, fill_value) # ~mask 는 1이 아닌 값들: 작은 수로 만듬(거의 0) 
        #fill_value에 실수형 텐서가 가질수 있는 최소값을 넣어 softmax가 0이 되도록함
        
        scaling = self.emb_size ** (1/2)
        att = F.softmax(energy, dim=-1) / scaling # [batch, head, query, key] # dim= -1 은 dimension인 key에 맞춤
        att = self.att_drop(att)
        # sum up over the third axis
        out = torch.einsum('bhal, bhlv -> bhav ', att, values) # dot product
        out = rearrange(out, "b h n d -> b n (h d)") # 8 heads 더해짐 # n: sequence length
        out = self.projection(out) # Linear layer
        return out

MHA = MultiHeadAttention().to(device)
MHA_output = MHA(patch_output)
print(MHA_output.shape) #torch.Size([16, 197, 768])

#%% #Residual 
 
class ResidualAdd(nn.Module):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
    
    def forward(self,x,**kwargs):
        res = x                   # residual
        x = self.fn(x,**kwargs) # original
        x += rest
        
        return x 
        
class FeedForwardBlock(nn.Sequential):
    def __init__(self, emb_size:int, expansion: int = 4, drop_p:float = 0.):
        super().__init__(
            nn.Linear(emb_size,expansion*emb_size),
            nn.GELU(),
            nn.Dropout(drop_p),
            nn.Linear(expansion * emb_size, emb_size)            
            ) 

Class residualAdd(nn.Module):








