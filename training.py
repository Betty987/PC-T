import torch
import time
import torch.nn.functional as F
from predictive_coding.config import GPTConfig
from predictive_coding.pc_layer import PCLayer
from model_architecture.pc_t_model import PCTransformer
from Data_preprocessing.dataloader import train_loader
from Data_preprocessing.config import Config
from utils.model_utils import load_tokenizer, reset_pc_modules
from matplotlib import pyplot as plt
from matplotlib.ticker import MaxNLocator

"""Usage: python training.py"""

def train(model, dataloader):
    model.train()
    total_energy = 0.0
    total_ce_loss = 0.0
    batch_count = 0

    for batch_idx, batch in enumerate(dataloader):
        input_ids = batch["input_ids"]
        target_ids = batch["target_ids"]
        logits = model(target_ids, input_ids)

        ce_loss = F.cross_entropy(
            logits.view(-1, logits.size(-1)),
            target_ids.view(-1),
            ignore_index=0
        )
        
        total_ce_loss += ce_loss.item()

        layer_energies = []
        for module in model.modules():
            if isinstance(module, PCLayer) and hasattr(module, "get_energy"):
                energy = module.get_energy()
                if energy is not None:
                    layer_energies.append(energy)
                if hasattr(module, "_head_similarity"):
                    _ = module._head_similarity_avg
                    _ = module._head_similarity_max

        # Compute average energy for current batch
        batch_energy = ce_loss.item() if not layer_energies else sum(layer_energies) / len(layer_energies)
        total_energy += batch_energy
        batch_count += 1
        
        if (batch_idx + 1) % 10 == 0:
            print(f"  Batch {batch_idx + 1}/{len(dataloader)} | Batch Energy: {batch_energy:.4f}", flush=True)

        reset_pc_modules(model)

    avg_energy = total_energy / batch_count if batch_count > 0 else 0.0
    avg_ce_loss = total_ce_loss / batch_count if batch_count > 0 else 0.0
    perplexity = torch.exp(torch.tensor(avg_ce_loss)).item()
    
    return avg_energy, perplexity

def main():
    tokenizer = load_tokenizer()
    vocab_size = Config.VOCAB_SIZE

    config = GPTConfig(
        vocab_size = vocab_size,
        block_size= 400, 
        n_embed=64,
        dropout=0.2096,
        local_learning_rate= 1.11e-03,
        T= 16,
        is_holding_error = True,
        num_heads=8,
        n_blocks=5,
        num_epochs= 50,
        update_bias=True,
        use_lateral = True,
        energy_fn_name="mse",
        eos_token_id = tokenizer.eos_token_id
    )

    model = PCTransformer(config)
    train_energies = []
    perplexities = []

    print("========== Training started ==========", flush=True) 
    # Measure total training time
    start_training_time = time.time()
    for epoch in range(config.num_epochs):
        print(f"Epoch {epoch+1} started", flush=True)
        avg_energy, perplexity = train(model, train_loader)
        train_energies.append(avg_energy)
        perplexities.append(perplexity)
        print(f"Epoch {epoch+1} | Avg Energy: {avg_energy:.4f} | Perplexity: {perplexity:.4f}", flush=True)
    total_training_time = time.time() - start_training_time
    print(f"Total Training Time: {total_training_time:.2f} seconds", flush=True)
    print("========== Training completed ==========", flush=True)

    # Saving trained model
    torch.save({"model_state": model.state_dict()}, "checkpoints/pc_transformer.pt")
    print("Model saved.")

    # Plotting average energy vs. epoch
    epochs = list(range(1, len(train_energies) + 1))
    plt.figure(figsize=(10, 6))
    plt.plot(epochs, train_energies, marker='o', linestyle='-', color='b', label='Average Batch Energy')
    plt.xlabel('Epoch')
    plt.ylabel('Average Batch Energy')
    plt.title('Average Batch Energy vs. Epoch')
    plt.grid(True)
    plt.legend()
    # Force x-axis to show only whole numbers
    plt.gca().xaxis.set_major_locator(MaxNLocator(integer=True))
    plt.tight_layout()
    #plt.savefig('assets/energy_plot.png')
    #plt.show()

if __name__ == "__main__":
    main()