from utils.tools import *
from network import *

import os
import torch
import torch.optim as optim
import time
import numpy as np

os.environ["CUDA_VISIBLE_DEVICES"] = "1"
torch.multiprocessing.set_sharing_strategy('file_system')

# DHN(AAAI2016)
# paper [Deep Hashing Network for Efficient Similarity Retrieval](http://ise.thss.tsinghua.edu.cn/~mlong/doc/deep-hashing-network-aaai16.pdf)
# code [DeepHash-tensorflow](https://github.com/thulab/DeepHash)

def get_config():
    config = {
        "alpha": 0.1,
        # "optimizer":{"type":  optim.SGD, "optim_params": {"lr": 0.05, "weight_decay": 10 ** -5}, "lr_type": "step"},
        "optimizer": {"type": optim.RMSprop, "optim_params": {"lr": 1e-5, "weight_decay": 10 ** -5}, "lr_type": "step"},
        "info": "[DHN]",
        "resize_size": 256,
        "crop_size": 224,
        "batch_size": 64,
        "net": AlexNet,
        # "net":ResNet,
        # "dataset": "cifar10",
        # "dataset": "nuswide_21",
        # "dataset": "nuswide_21_m",
        # "dataset": "nuswide_81_m",
        "dataset": "coco",
        # "dataset":"imagenet",
        "epoch": 90,
        "test_map": 15,
        "save_path": "save/DHN",
        "GPU": True,
        # "GPU":False,
        "bit_list": [48],
    }
    config = config_dataset(config)
    return config


class DHNLoss(torch.nn.Module):
    def __init__(self, config, bit):
        super(DHNLoss, self).__init__()
        self.U = torch.zeros(config["num_train"], bit).float()
        self.Y = torch.zeros(config["num_train"], config["n_class"]).float()

        if config["GPU"]:
            self.U = self.U.cuda()
            self.Y = self.Y.cuda()

    def forward(self, u, y, ind, config):
        self.U[ind, :] = u.data
        self.Y[ind, :] = y.float()

        s = (y @ self.Y.t() > 0).float()
        inner_product = u @ self.U.t() * 0.5
        if config["GPU"]:
            log_trick = torch.log(1 + torch.exp(-torch.abs(inner_product))) \
                        + torch.max(inner_product, torch.FloatTensor([0.]).cuda())
        else:
            log_trick = torch.log(1 + torch.exp(-torch.abs(inner_product))) \
                        + torch.max(inner_product, torch.FloatTensor([0.]))
        loss = log_trick - s * inner_product
        loss1 = loss.mean()
        loss2 = config["alpha"] * (u.abs() - 1).abs().mean()

        return loss1 + loss2


def train_val(config, bit):
    train_loader, test_loader, dataset_loader, num_train, num_test = get_data(config)
    config["num_train"] = num_train
    net = config["net"](bit)
    if config["GPU"]:
        net = net.cuda()

    optimizer = config["optimizer"]["type"](net.parameters(), **(config["optimizer"]["optim_params"]))

    criterion = DHNLoss(config, bit)

    Best_mAP = 0

    for epoch in range(config["epoch"]):

        current_time = time.strftime('%H:%M:%S', time.localtime(time.time()))

        print("%s[%2d/%2d][%s] bit:%d, dataset:%s, training...." % (
            config["info"], epoch + 1, config["epoch"], current_time, bit, config["dataset"]), end="")

        net.train()

        train_loss = 0
        for image, label, ind in train_loader:
            if config["GPU"]:
                image, label = image.cuda(), label.cuda()

            optimizer.zero_grad()
            u = net(image)

            loss = criterion(u, label.float(), ind, config)
            train_loss += loss.item()

            loss.backward()
            optimizer.step()

        train_loss = train_loss / len(train_loader)

        print("\b\b\b\b\b\b\b loss:%.3f" % (train_loss))

        if (epoch + 1) % config["test_map"] == 0:
            # print("calculating test binary code......")
            tst_binary, tst_label = compute_result(test_loader, net, usegpu=config["GPU"])

            # print("calculating dataset binary code.......")\
            trn_binary, trn_label = compute_result(dataset_loader, net, usegpu=config["GPU"])

            # print("calculating map.......")
            mAP = CalcTopMap(trn_binary.numpy(), tst_binary.numpy(), trn_label.numpy(), tst_label.numpy(),
                             config["topK"])

            if mAP > Best_mAP:
                Best_mAP = mAP

                if "save_path" in config:
                    if not os.path.exists(config["save_path"]):
                        os.makedirs(config["save_path"])
                    print("save in ", config["save_path"])
                    np.save(os.path.join(config["save_path"], config["dataset"] + str(mAP) + "-" + "trn_binary.npy"),
                            trn_binary.numpy())
                    torch.save(net.state_dict(),
                               os.path.join(config["save_path"], config["dataset"] + "-" + str(mAP) + "-model.pt"))
            print("%s epoch:%d, bit:%d, dataset:%s, MAP:%.3f, Best MAP: %.3f" % (
                config["info"], epoch + 1, bit, config["dataset"], mAP, Best_mAP))
            print(config)


if __name__ == "__main__":
    config = get_config()
    print(config)
    for bit in config["bit_list"]:
        train_val(config, bit)
