import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torch.utils.data import DataLoader
import time
from bayes_opt import BayesianOptimization
import exp
import dataset

class ConvLSTM(nn.Module):

    def __init__(self, input_dim, hidden_dim, output_dim, num_layers, num_filters, filter_size, dropout, use_bn, window_len):

        super(ConvLSTM, self).__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim

        self.num_layers = num_layers
        self.num_filters = num_filters
        self.filter_size = filter_size

        self.dropout = dropout
        self.use_bn = use_bn
        self.window_len = window_len

        # Layers 2-5
        self.conv1 = nn.Conv1d(input_dim, num_filters, filter_size)
        self.conv2 = nn.Conv1d(num_filters, num_filters, filter_size)
        self.conv3 = nn.Conv1d(num_filters, num_filters, filter_size)
        self.conv4 = nn.Conv1d(num_filters, num_filters, filter_size)

        # Layers 6-7 - each dense layer has LSTM cells
        self.lstm1 = nn.LSTM(num_filters, hidden_dim, num_layers, batch_first=True)
        self.lstm2 = nn.LSTM(hidden_dim, hidden_dim, num_layers, batch_first=True)
        self.lstm3 = nn.LSTM(hidden_dim, hidden_dim, num_layers, batch_first=True)
        self.lstm4 = nn.LSTM(hidden_dim, hidden_dim, num_layers, batch_first=True)
        self.lstm5 = nn.LSTM(hidden_dim, hidden_dim, num_layers, batch_first=True)

        # Layer 9 - prepare for softmax
        self.fc = nn.Linear(hidden_dim, output_dim)
        self.dropout = nn.Dropout(dropout)

    def init_hidden(self, input_shape):
        '''
        Initializes hidden state

        Create two new tensors with sizes n_layers x batch_size x n_hidden,
        initialized to zero, for hidden state and cell state of LSTM
        '''
        weight = next(self.parameters()).data

        # changed this from batch_size to 3*batch_size
        hidden = (weight.new(self.num_layers, input_shape[0], self.hidden_dim).zero_(),
        weight.new(self.num_layers, input_shape[0], self.hidden_dim).zero_())

        return hidden

    def forward(self, x):

        # Layer 1 - flatten (see -1)
        self.hidden = self.init_hidden(x.shape)
        x = x.view(-1, self.input_dim, self.window_len)

        # Layers 2-5 - RELU
        x = F.relu(self.conv1(x))
        x = F.relu(self.conv2(x))
        x = F.relu(self.conv3(x))
        x = F.relu(self.conv4(x))

        # Layers 5 and 6 - flatten
        x = x.view(1, -1, self.num_filters)

        # Layers 6-8 - hidden layers
        x, self.hidden = self.lstm1(x, self.hidden)
        x, self.hidden = self.lstm2(x, self.hidden)
        x, self.hidden = self.lstm3(x, self.hidden)
        x, self.hidden = self.lstm4(x, self.hidden)
        x, self.hidden = self.lstm5(x, self.hidden)

        # Layers 8 - flatten, fully connected for softmax. Not sure what dropout does here
        x = x.contiguous().view(-1, self.hidden_dim)
        x = self.dropout(x)
        out = self.fc(x[:, -1])

        # out = out.view(self.batch_size, -1, self.output_dim)[:, -1, :]

        return out


class LSTM(nn.Module):

    def __init__(self, input_dim, hidden_dim, output_dim, num_layers, dropout, use_bn):

        super(LSTM, self).__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim
        self.num_layers = num_layers

        self.dropout = dropout
        self.use_bn = use_bn

        self.lstm = nn.LSTM(self.input_dim, self.hidden_dim, self.num_layers, batch_first=True)
        self.fc = nn.Linear(self.hidden_dim, output_dim)

    def init_hidden(self, input_shape):
        return (torch.zeros(self.num_layers, input_shape[0], self.hidden_dim),
        torch.zeros(self.num_layers, input_shape[0], self.hidden_dim))

    def forward(self, x):
        self.hidden = self.init_hidden(x.shape)
        lstm_out, self.hidden = self.lstm(x, self.hidden)
        out = self.fc(lstm_out[:, -1])
        return out

class CNN(nn.Module):
    def __init__(self, input_dim, output_dim, num_filters, filter_size, dropout, window_len):
        super(CNN, self).__init__()
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.num_filters = num_filters
        self.filter_size = filter_size
        self.dropout = dropout
        self.window_len = window_len

        self.conv1 = nn.Conv1d(input_dim, num_filters, filter_size)
        self.pool = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv1d(num_filters, num_filters, filter_size)
        self.conv3 = nn.Conv1d(num_filters, num_filters, filter_size)

        self.fc = nn.Linear(num_filters, output_dim)

    def forward(self, x, batch_size):
        x = x.view(-1, self.input_dim, self.window_len)
        print('forward 1:', x.shape)
        '''
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = self.pool(F.relu(self.conv3(x)))
        위의 식으로 코드 돌리면 filter 개수가 절반이 되어서 에러가 남
        '''
        x = F.relu(self.conv1(x))
        print('forward 2:',x.shape)
        x = F.relu(self.conv2(x))
        print('forward 3:',x.shape)
        x = F.relu(self.conv3(x))
        print('forward 4:',x.shape)

        x = x.view(1, -1, self.num_filters)
        print('forward 5:',x.shape)
        #x = self.dropout(x)
        out = self.fc(x)
        print('forward 6:',out.shape)
        #out = out.view(batch_size, -1, self.output_dim)[:, -1, :]
        out = np.squeeze(out)
        print('forward 7:',out.shape)

        return out

class Manager():
    def __init__(self, args):
        self.trainset = dataset.NumDataset('data/FakeData.csv', args.x_frames, args.y_frames, args.str_len)
        self.valset = dataset.NumDataset('data/FakeData.csv', args.x_frames, args.y_frames, args.str_len)
        self.testset = dataset.NumDataset('data/FakeData.csv', args.x_frames, args.y_frames, args.str_len)
        self.device = args.device

        # Select the model type
        if args.model == 'ConvLSTM':
            self.model = ConvLSTM(args.input_dim, args.hid_dim, args.y_frames, args.n_layers, args.n_filters,
                                  args.filter_size, args.dropout, args.use_bn, args.str_len)
        elif args.model == 'LSTM':
            self.model = LSTM(args.input_dim, args.hid_dim, args.y_frames, args.n_layers, args.dropout, args.use_bn)
        elif args.model == 'CNN':
            self.model = CNN(args.input_dim, args.y_frames, args.n_filters, args.filter_size, args.dropout, args.str_len)
        else:
            raise ValueError('In-valid model choice')

        self.model.to(self.device)

        self.pbounds = {
        'learning_rate': args.lr,
        'batch_size': args.batch_size
        }

        self.bayes_optimizer = BayesianOptimization(
        f=self.train,
        pbounds=self.pbounds
        )

    def train(self, learning_rate, batch_size):

        model = self.model
        batch_size = round(batch_size)
        print('batch size: ', batch_size)
        loss_fn = torch.nn.CrossEntropyLoss()

        trainloader = DataLoader(self.trainset, batch_size=batch_size,
        shuffle=True, drop_last=True)

        optimizer = optim.Adam(model.parameters(), lr=learning_rate)
        model.train()
        model.zero_grad()
        optimizer.zero_grad()

        train_acc = 0.0
        train_loss = 0.0

        for i, (X, y) in enumerate(trainloader):

            print('X1: ', X.shape)
            print('y2: ', y.shape)

            X = X.transpose(0, 1).float().to(self.device)
            print('X2: ', X.shape)

            y_true = y.long().to(self.device)
            print('y_true shape: ', y_true.shape)
            y_1 = y_true.view(-1)
            print('y_1 shape: ', y_1.shape)

            model.zero_grad()
            optimizer.zero_grad()
            if model == 'ConvLSTM' or model == 'LSTM':
                model.hidden = [hidden.to(args.device) for hidden in model.init_hidden()]
            print('batch size final: ', batch_size)
            y_pred = model(X, batch_size)
            print('y_pred shape', y_pred.shape)
            loss = loss_fn(y_pred, y_true.view(-1))
            loss.backward()
            optimizer.step()

            _, y_pred = torch.max(y_pred.data, 1)
            train_loss += loss.item()
            train_acc += (y_pred == y_true).sum()

        train_loss = train_loss / len(trainloader)
        train_acc = train_acc / len(trainloader)
        train_acc = float(train_acc)

        return train_loss, train_acc

    def validate(self, loss_fn, args, batch_size):
        model = self.model
        batch_size = round(batch_size)
        valloader = DataLoader(self.valset, batch_size=args.batch_size,
        shuffle=False, drop_last=True)
        model.eval()

        val_acc = 0.0
        val_loss = 0.0
        with torch.no_grad():
            for i, (X, y) in enumerate(valloader):

                X = X.transpose(0, 1).float().to(args.device)
                y_true = y.long().to(args.device)
                if args.model == 'ConvLSTM' or args.model == 'LSTM':
                    model.hidden = [hidden.to(args.device) for hidden in model.init_hidden()]

                y_pred = model(X, batch_size)
                loss = loss_fn(y_pred, y_true.view(-1))

                _, y_pred = torch.max(y_pred.data, 1)
                val_loss += loss.item()
                val_acc += (y_pred == y_true).sum()

        val_loss = val_loss / len(valloader)
        val_acc = val_acc / len(valloader)
        val_acc = float(val_acc)

        return val_loss, val_acc

    def test(self, args):
        model = self.model
        testloader = DataLoader(self.testset, batch_size=args.inference_batch_size,
                                shuffle=False, drop_last=True)
        model.eval()

        test_acc = 0.0
        with torch.no_grad():
            for i, (X, y) in enumerate(testloader):

                X = X.transpose(0, 1).float().to(args.device)
                y_true = y[:, 0].long().to(args.device)
                if args.model == 'ConvLSTM' or args.model == 'LSTM':
                    model.hidden = [hidden.to(args.device) for hidden in model.init_hidden()]

                y_pred = model(X)
                _, y_pred = torch.max(y_pred.data, 1)
                test_acc += (y_pred == y_true).sum()

        test_acc = test_acc / len(testloader)
        test_acc = float(test_acc)
        return test_acc

def experiment(mode, args):

    # ===== List for epoch-wise data ====== #
    train_losses = []
    val_losses = []
    train_accs = []
    val_accs = []
    # ===================================== #

    loss_fn = torch.nn.CrossEntropyLoss()
    manager = Manager(args)

    if args.mode == 'train':
        for epoch in range(args.epoch):  # loop over the dataset multiple times
            ts = time.time()
            print('Start training ... ')
            manager.bayes_optimizer.maximize(args.init_points, args.n_iter, acq='ei', xi=0.01)
            exp.save_exp_result(manager)

            print('Start validation ... ')
            val_loss, val_acc = manager.validate(loss_fn, args)
            te = time.time()

            # ====== Add Epoch Data ====== #
            train_losses.append(train_loss)
            val_losses.append(val_loss)
            train_accs.append(train_acc)
            val_accs.append(val_acc)
            # ============================ #

            print(
                'Epoch {}, Acc(train/val): {:2.2f}/{:2.2f}, Loss(train/val) {:2.5f}/{:2.5f}. Took {:2.2f} sec'.format(epoch, train_acc, val_acc, train_loss, val_loss, te - ts))
    elif args.mode == 'test':
        test_acc = manager.test(args)

    # ======= Add Result to Dictionary ======= #
    result = {}
    if args.mode == 'train':
        result['train_losses'] = train_losses
        result['val_losses'] = val_losses
        result['train_accs'] = train_accs
        result['val_accs'] = val_accs
        result['train_acc'] = train_acc
        result['val_acc'] = val_acc
    elif args.mode == 'test':
        result['test_acc'] = test_acc

    return vars(args), result
