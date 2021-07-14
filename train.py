import yaml
import torch
import os
import numpy as np
import logging
logging.basicConfig(level = logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from tqdm import tqdm
from model import Model
from dataset import LEDataset
from transformers_model.models.bert.tokenization_bert import BertTokenizer
from torch.utils.data import DataLoader

from torch.optim import AdamW
from torch.nn.functional import cross_entropy


def train(config):

    CURRENT_DIR = config["CURRENT_DIR"]

    train_set, eval_set, test_set = load_dataset(config)
    logger.info("加载模型...")
    model = Model(config)
    if config["use_cuda"] and torch.cuda.is_available():
        model = model.cuda()
    logger.info("加载模型完成...")
    train_dataloader = DataLoader(dataset=train_set, batch_size=config["batch_size"], shuffle=True)
    eval_dataloader = DataLoader(dataset=eval_set, batch_size=config["batch_size"], shuffle=True)
    test_dataloader = DataLoader(dataset=test_set, batch_size=config["batch_size"], shuffle=True)

    optimizer = AdamW(model.parameters(), config["LR"])
    # scheduler = WarmupLinearSchedule(optimizer, warmup_steps=args.warmup_steps, t_total=t_total)

    # Train!
    logger.info("***** Running training *****")
    logger.info("  Num train examples = %d", len(train_dataloader)*config["batch_size"])
    logger.info("  Num eval examples = %d", len(eval_dataloader)*config["batch_size"])
    logger.info("  Num test examples = %d", len(test_dataloader)*config["batch_size"])
    logger.info("  Num Epochs = %d", config["EPOCH"])
    logger.info("  Learning rate = %d", config["LR"])

    model.train()

    for epoch in range(config["EPOCH"]):
        for index, batch in enumerate(train_dataloader):
            optimizer.zero_grad()
            input_ids, attention_mask, token_type_ids = \
                batch[0]["input_ids"].squeeze(), batch[0]["attention_mask"].squeeze(), batch[0]["token_type_ids"].squeeze()
            label = batch[1]
            if config["use_cuda"] and torch.cuda.is_available():
                input_ids, attention_mask, token_type_ids = \
                input_ids.cuda(), attention_mask.cuda(), token_type_ids.cuda()
                label = label.cuda()
            model_output = model(input_ids, attention_mask, token_type_ids)
            train_loss = cross_entropy(model_output, label)
            train_loss.backward()
            optimizer.step()

            if index % 10 == 0 and index > 0:
                logger.info("train epoch {}/{} batch {}/{} loss {}".format(str(epoch), str(config["EPOCH"]), str(index), str(len(train_dataloader)), str(train_loss.item())))
            if index % 1000 == 0:
                evaluate(config, model, eval_dataloader)
                if index > 0:
                    checkpoint_name = os.path.join(config["checkpoint_path"],"checkpoint-epoch{}-batch{}.bin".format(str(epoch), str(index)))
                    torch.save(model.state_dict(), checkpoint_name)
                    logger.info("saved model!")
            model = model.train()


def evaluate(config, model, eval_dataloader):
    # test
    model = model.eval()
    logger.info("eval!")
    loss_sum = 0

    correct = torch.zeros(1).squeeze().cuda()
    total = torch.zeros(1).squeeze().cuda()
    # 创建混淆矩阵
    confuse_matrix = np.zeros((3, 3))

    for index, batch in enumerate(eval_dataloader):
        input_ids, attention_mask, token_type_ids = \
                batch[0]["input_ids"].squeeze(), batch[0]["attention_mask"].squeeze(), batch[0]["token_type_ids"].squeeze()
        label = batch[1]
        if config["use_cuda"] and torch.cuda.is_available():
            input_ids, attention_mask, token_type_ids = \
            input_ids.cuda(), attention_mask.cuda(), token_type_ids.cuda()
            label = label.cuda()
        model_output = model(input_ids, attention_mask, token_type_ids)
        eval_loss = cross_entropy(model_output, label)
        loss_sum = loss_sum + eval_loss.item()

        pred = torch.argmax(model_output, dim=1)

        correct += (pred == label).sum().float()
        total += len(label)
        for index in range(len(pred)):
            confuse_matrix[label[index]][pred[index]] = confuse_matrix[label[index]][pred[index]] + 1
    
    logger.info("eval loss: {}".format(str(loss_sum / (len(eval_dataloader)))))
    logger.info("eval accu: {}".format(str((correct/total).cpu().detach().data.numpy())))
    logger.info("confuse_matrix:")
    
    logger.info("{}   |   {}   |   {}".format(str(confuse_matrix[0][0]), str(confuse_matrix[0][1]), str(confuse_matrix[0][2])))
    logger.info("{}   |   {}   |   {}".format(str(confuse_matrix[1][0]), str(confuse_matrix[1][1]), str(confuse_matrix[1][2])))
    logger.info("{}   |   {}   |   {}".format(str(confuse_matrix[2][0]), str(confuse_matrix[2][1]), str(confuse_matrix[2][2])))

    logger.info("软件开发 精度 {} 召回率 {}".format(str(confuse_matrix[0][0] / (confuse_matrix[0][0] + confuse_matrix[1][0] + confuse_matrix[2][0])), str(confuse_matrix[0][0] / (confuse_matrix[0][0] + confuse_matrix[0][1] + confuse_matrix[0][2]))))
    logger.info("会计审计 精度 {} 召回率 {}".format(str(confuse_matrix[1][1] / (confuse_matrix[1][1] + confuse_matrix[0][1] + confuse_matrix[2][1])), str(confuse_matrix[1][1] / (confuse_matrix[1][1] + confuse_matrix[1][0] + confuse_matrix[1][2]))))
    logger.info("汽车销售 精度 {} 召回率 {}".format(str(confuse_matrix[2][2] / (confuse_matrix[2][2] + confuse_matrix[0][2] + confuse_matrix[1][2])), str(confuse_matrix[2][2] / (confuse_matrix[2][2] + confuse_matrix[2][0] + confuse_matrix[2][1]))))

    


def load_dataset(config):
    CURRENTDIR = config["CURRENT_DIR"]
    # TRAIN_CACHED_PATH = os.path.join(CURRENTDIR, "data/train/train_cached.bin")
    # EVAL_CACHED_PATH = os.path.join(CURRENTDIR, "data/eval/eval_cached.bin")
    # TEST_CACHED_PATH = os.path.join(CURRENTDIR, "data/test/test_cached.bin")
    #
    # if os.path.exists(TEST_CACHED_PATH):
    #     torch.load()

    TRAIN_SOURCE_PATH = os.path.join(CURRENTDIR, config["TRAIN_DIR"])
    EVAL_SOURCE_PATH = os.path.join(CURRENTDIR, config["EVAL_DIR"])
    TEST_SOURCE_PATH = os.path.join(CURRENTDIR, config["TEST_DIR"])

    tokenizer = BertTokenizer.from_pretrained(config["bert_model_path"])
    logger.info("构建数据集...")
    train_set = construct_dataset(tokenizer, TRAIN_SOURCE_PATH)
    eval_set = construct_dataset(tokenizer, EVAL_SOURCE_PATH)
    test_set = construct_dataset(tokenizer, TEST_SOURCE_PATH)
    logger.info("构建完成...训练集{}条数据，验证集{}条数据，测试集{}条数据...".format(len(train_set), len(eval_set), len(test_set)))
    return train_set, eval_set, test_set


def construct_dataset(tokenizer, SOURCE_PATH):
    tokenized_list = list()
    label_list = list()
    with open(SOURCE_PATH, "r", encoding="utf-8") as train_set:
        data = train_set.readlines()
        for line in tqdm(data):
            line = line.strip()
            sequence, label = line[:-2], line[-1]
            # print(sequence, label)
            # break
            sequence_tokenized = tokenizer(sequence, return_tensors="pt", max_length=20, padding="max_length",
                                           truncation=True)
            tokenized_list.append(sequence_tokenized)
            label_list.append(label)

    return LEDataset(tokenized_list, label_list)


if __name__ == '__main__':
    with open(r'config.yaml', 'r', encoding='utf-8') as f:
        result = f.read()
        config = yaml.load(result)
    train(config)
