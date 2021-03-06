import pytest
from fastai import *
from fastai.text import *

pytestmark = pytest.mark.integration

def read_file(fname):
    texts = []
    with open(fname, 'r') as f: texts = f.readlines()
    labels = [0] * len(texts)
    df = pd.DataFrame({'labels':labels, 'texts':texts}, columns = ['labels', 'texts'])
    return df

def prep_human_numbers():
    path = untar_data(URLs.HUMAN_NUMBERS)
    df_trn = read_file(path/'train.txt')
    df_val = read_file(path/'valid.txt')
    return path, df_trn, df_val

@pytest.fixture(scope="module")
def learn():
    path, df_trn, df_val = prep_human_numbers()
    df = df_trn.append(df_val)
    data = (TextList.from_df(df, path, cols='texts')
                .split_by_idx(list(range(len(df_trn),len(df))))
                .label_for_lm()
                .add_test(df['texts'].iloc[:200].values)
                .databunch())
    learn = language_model_learner(data, emb_sz=100, nl=1, drop_mult=0.)
    learn.fit_one_cycle(2, 0.1)
    return learn

@pytest.mark.slow
def manual_seed(seed=42):
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False

def test_val_loss(learn): assert learn.validate()[1] > 0.3

@pytest.mark.slow
def test_qrnn_works_with_no_split():
    gc.collect()
    manual_seed()
    path, df_trn, df_val = prep_human_numbers()
    data = TextLMDataBunch.from_df(path, df_trn, df_val, tokenizer=Tokenizer(BaseTokenizer))
    learn = language_model_learner(data, emb_sz=100, nl=1, drop_mult=0.1, qrnn=True)
    learn = LanguageLearner(data, learn.model, bptt=70) #  remove the split_fn
    learn.fit_one_cycle(2, 0.1)
    assert learn.validate()[1] > 0.3

@pytest.mark.slow
def test_qrnn_works_if_split_fn_provided():
    gc.collect()
    manual_seed()
    path, df_trn, df_val = prep_human_numbers()
    data = TextLMDataBunch.from_df(path, df_trn, df_val, tokenizer=Tokenizer(BaseTokenizer))
    learn = language_model_learner(data, emb_sz=100, nl=1, drop_mult=0.1, qrnn=True) # it sets: split_func=lm_split
    learn.fit_one_cycle(2, 0.1)
    assert learn.validate()[1] > 0.3

def test_vocabs(learn):
    for ds in [learn.data.valid_ds, learn.data.test_ds]:
        assert len(learn.data.train_ds.vocab.itos) == len(ds.vocab.itos)
        assert np.all(learn.data.train_ds.vocab.itos == ds.vocab.itos)

def test_classifier(learn):
    lm_vocab = learn.data.vocab
    data = (TextList.from_df(df, path, cols='texts', vocab = lm_vocab)
                .split_by_idx(list(range(len(df_trn),len(df))))
                .label_from_df(cols=0)
                .add_test(df['texts'].iloc[:200].values)
                .databunch())
    for ds in [data.train_ds, data.valid_ds, data.test_ds]:
        assert len(lm_vocab.itos) == len(ds.vocab.itos)
        assert np.all(lm_vocab.itos == ds.vocab.itos)

@pytest.mark.skip(reason="need to update")
def text_df(n_labels):
    data = []
    texts = ["fast ai is a cool project", "hello world"]
    for ind, text in enumerate(texts):
        sample = {}
        for label in range(n_labels): sample[label] = ind%2
        sample["text"] = text
        data.append(sample)
    df = pd.DataFrame(data)
    return df

@pytest.mark.skip(reason="need to update")
def test_classifier():
    for n_labels in [1, 8]:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'tmp')
        os.makedirs(path)
        try:
            df = text_df(n_labels=n_labels)
            data = TextClasDataBunch.from_df(path, train_df=df, valid_df=df, label_cols=list(range(n_labels)), text_cols=["text"])
            classifier = text_classifier_learner(data)
            assert last_layer(classifier.model).out_features == n_labels if n_labels > 1 else n_labels+1
        finally:
            shutil.rmtree(path)

# XXX: may be move into its own test module?
import gc
# everything created by this function should be freed at its exit
def clean_destroy_block():
    path, df_trn, df_val = prep_human_numbers()
    data = TextLMDataBunch.from_df(path, df_trn, df_val, tokenizer=Tokenizer(BaseTokenizer))
    learn = language_model_learner(data, emb_sz=100, nl=1, drop_mult=0.)
    learn.lr_find()

@pytest.mark.skip(reason="memory leak to be fixed")
def test_mem_leak():
    gc.collect()
    garbage_before = len(gc.garbage)  # should be 0 already, or something leaked earlier
    assert garbage_before == 0
    clean_destroy_block()
    gc_collected = gc.collect() # should be 0 too - !0 means we have circular references
    assert gc_collected == 0
    garbage_after = len(gc.garbage)  # again, should be 0, or == garbage_before
    assert garbage_after == 0
