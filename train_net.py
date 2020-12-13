import xception
import separable_net
import pvc1_loader

import datetime
import itertools

import torch
from torch import nn
from torch import optim
from torch.utils.tensorboard import SummaryWriter
import torch.autograd.profiler as profiler

import os

def get_all_layers(net, prefix=[]):
    if hasattr(net, '_modules'):
        lst = []
        for name, layer in net._modules.items():
            full_name = '_'.join((prefix + [name]))
            lst = lst + [(full_name, layer)] + get_all_layers(layer, prefix + [name])
        return lst
    else:
        return []


def save_state(net, title, output_dir):
    datestr = str(datetime.datetime.now()).replace(':', '-')
    torch.save(net.state_dict(), os.path.join(output_dir, f'{title}-{datestr}.pt'))

def main(data_root='/storage/crcns/pvc1/', 
         output_dir='/storage/trained/xception2d'):

    print("Main")
    # Train a network
    try:
        os.makedirs(data_root)
    except FileExistsError:
        pass

    try:
        os.makedirs(output_dir)
    except FileExistsError:
        pass
    
    writer = SummaryWriter()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device == 'cpu':
        print("No CUDA! Sad!")

    print("Download data")
    # pvc1_loader.download(data_root, 'https://storage.googleapis.com/vpl-bucket/')

    print("Loading data")

    trainset = pvc1_loader.PVC1(os.path.join(data_root, 'crcns-ringach-data'), 
                                split='train', ntau=6)
    trainloader = torch.utils.data.DataLoader(trainset, 
                                              batch_size=1, 
                                              shuffle=True)

    testset = pvc1_loader.PVC1(os.path.join(data_root, 'crcns-ringach-data'), 
                               split='test', ntau=6)
    testloader = torch.utils.data.DataLoader(testset, 
                                             batch_size=1, 
                                             shuffle=True)
    testloader_iter = iter(testloader)

    print("Init models")

    subnet = xception.Xception(start_kernel_size=7, 
                               nblocks=0, 
                               nstartfeats=32)
    subnet.to(device=device)

    

    net = separable_net.LowRankNet(subnet, 
                                   1, 
                                   trainset.total_electrodes, 
                                   32, 
                                   109, 109, trainset.ntau).to(device)

    net.to(device=device)

    layers = get_all_layers(net)

    criterion = nn.MSELoss()
    # optimizer = optim.SGD(net.parameters(), lr=1e-2, momentum=0.9)
    optimizer = optim.Adam(net.parameters(), lr=1e-2)

    m, n = 0, 0
    print_frequency = 25
    test_loss = 0.0
    
    try:
        for epoch in range(20):  # loop over the dataset multiple times
            running_loss = 0.0
            for i, data in enumerate(trainloader, 0):
                # get the inputs; data is a list of [inputs, labels]
                (X, rg), labels = data
                X, rg, labels = X.to(device), rg.to(device), labels.to(device)

                # zero the parameter gradients
                optimizer.zero_grad()
                outputs = net((X, rg))

                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()

                # print statistics
                running_loss += loss.item()
                
                writer.add_scalar('Labels/mean', labels.mean(), n)
                writer.add_scalar('Labels/std', labels.std(), n)
                writer.add_scalar('Outputs/mean', outputs.mean(), n)
                writer.add_scalar('Outputs/std', outputs.std(), n)
                writer.add_scalar('Loss/train', loss.item(), n)
                
                if i % print_frequency == print_frequency - 1:
                    for name, layer in layers:
                        if hasattr(layer, 'weight'):
                            writer.add_scalar(f'Weights/{name}/mean', 
                                            layer.weight.mean(), n)
                            writer.add_scalar(f'Weights/{name}/std', 
                                            layer.weight.std(), n)
                            writer.add_histogram(f'Weights/{name}/hist', 
                                            layer.weight.view(-1), n)

                    for name, param in net._parameters.items():
                        writer.add_scalar(f'Weights/{name}/mean', 
                                        param.mean(), n)
                        writer.add_scalar(f'Weights/{name}/std', 
                                        param.std(), n)
                        writer.add_histogram(f'Weights/{name}/hist', 
                                        param.view(-1), n)

                    writer.add_images('Weights/conv1d/img', subnet.conv1.weight, n)

                    print('[%d, %5d] average train loss: %.3f' % (epoch + 1, i + 1, running_loss / print_frequency ))
                    running_loss = 0

                if i % 7 == 0:
                    try:
                        test_data = next(testloader_iter)
                    except StopIteration:
                        testloader_iter = iter(testloader)
                        test_data = next(testloader_iter)
                    
                    # get the inputs; data is a list of [inputs, labels]
                    (X, rg), labels = test_data
                    X, rg, labels = X.to(device), rg.to(device), labels.to(device)

                    outputs = net((X, rg))
                    loss = criterion(outputs, labels)
                    writer.add_scalar('Loss/test', loss.item(), n)

                    test_loss += loss.item()
                    m += 1

                    if m == print_frequency:
                        print(f"Test accuracy: {test_loss /  print_frequency:.3f}")
                        test_loss = 0
                        m = 0

                n += 1

                if n % 10000 == 0:
                    save_state(net, f'xception.ckpt{n}', output_dir)
                    
    except KeyboardInterrupt:
        save_state(net, f'xception.ckpt{n}', output_dir)

if __name__ == "__main__":
    print("Getting into main")
    main('.', 'models/shallow')

