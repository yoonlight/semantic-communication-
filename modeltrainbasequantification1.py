#第二重要的部分，用于训练使用,这个是act =False，使用act版本



import os, platform
import torch
from math import log
import torch.nn as nn
import torch.nn.functional as F
from data_loader import Dataset_sentence, collate_func
from model import make_model,subsequent_mask,make_std_mask,make_decoder
from utils import Normlize_tx, Channel, Crit, clip_gradient
import torch.utils.data as data
import torch.optim as optim
import numpy as np

#_snr = 12
_iscomplex = True
batch_size = 64
epochs = 61
learning_rate = 1e-5  #1e-3可能过高 需要调成 3e-4 或者 5e-4效果更加
epoch_start = 51  # only used when loading ckpt

# set path
save_model_path = "./ckpt/"
if 'Windows' in platform.system():
    data_path = r'C:\Users\10091\Desktop\Py\dataset'
else:
    data_path = '/data/zqy/act1/dataset'

if not os.path.exists(save_model_path): os.makedirs(save_model_path)



# device and cuda
use_cuda = torch.cuda.is_available()
device = torch.device("cuda:0" if use_cuda else "cpu")
data_parallel = False

train_loader_params = {'batch_size': batch_size,
                       'shuffle': True, 'num_workers':8,
                       'collate_fn': lambda x: collate_func(x),
                       'drop_last': True}
data_train = Dataset_sentence(_path = data_path)
train_data_loader = data.DataLoader(data_train,**train_loader_params)

vocab_size = data_train.get_dict_len()

tmp_model = make_model(vocab_size,vocab_size,act1=False,act2=False).to(device)  
tmp_model.load_state_dict(torch.load('./ckpt/TRY1_epoch{}.pth'.format(epoch_start-1)))
for name,param in tmp_model.named_parameters():
    param.requires_grad = False

class LBSign(torch.autograd.Function):

    @staticmethod
    def forward(ctx, input):
        return torch.sign(input)

    @staticmethod
    def backward(ctx, grad_output):
        return grad_output.clamp_(-1, 1)

sign = LBSign.apply

class DENSE(nn.Module):
    def __init__(self):
        super(DENSE,self).__init__()
        self.layer1=nn.Linear(16,30)
        self.layer2=nn.Linear(30,16)
        
    def Q(self,x):
        return sign(self.layer1(x))
    
    def dQ(self,x):
        return self.layer2(x)

lianghua=DENSE().to(device)

tmp_model=tmp_model.eval()

criterion = nn.MSELoss()

channel = Channel(_iscomplex=_iscomplex)

_params = list(lianghua.parameters())
optimizer = torch.optim.Adam(_params, lr=learning_rate)
scheduler = optim.lr_scheduler.MultiStepLR(optimizer, milestones = [10,20,30,40], gamma = 0.3)
crit = Crit()



def train(model, device, train_loader, optimizer, epoch):

    # set model as training mode
    model.train()
    if data_parallel: torch.cuda.synchronize()
    print('--------------------epoch: %d' % epoch)

    for batch_idx, (train_sents, len_batch) in enumerate(train_loader):
        train_sents = train_sents.to(device)  
        len_batch = len_batch.to(device) 

        optimizer.zero_grad()
        src = train_sents[:, 1:]
        trg = train_sents[:, :-1]
        trg_y = train_sents[:, 1:]
        src_mask = (src != 0).unsqueeze(-2).to(device)
        tgt_mask = make_std_mask(trg).to(device)

        output= tmp_model.encode(src, src_mask)
        out= model.Q(output)
        snr = np.random.randint(-2,5)
        out= channel.agwn_physical_layer(out, _snr=snr)
        out= sign(out)
        out= model.dQ(out)
        loss = criterion(output,out)


        loss.backward()
        clip_gradient(optimizer, 0.1) 
        optimizer.step()

        if batch_idx%4000==0:
            print('[%4d / %4d]    '%(batch_idx, epoch) , '    loss = ', loss.item())


    if epoch%10==0: #== 0:
        # save Pytorch models of best record
        torch.save(model.module.state_dict() if data_parallel else model.state_dict(),
                   os.path.join(save_model_path, 'TRY1dense_epoch{}.pth'.format(epoch)))
        print("Epoch {} model saved!".format(epoch + 1))


# start training
for epoch in range(1, epochs):
    train(lianghua, device, train_data_loader, optimizer, epoch)
    scheduler.step()
    #validation(embed_encoder, rnn_decoder, device, optimizer, val_data_loader, epoch)

# optimizer.param_groups


