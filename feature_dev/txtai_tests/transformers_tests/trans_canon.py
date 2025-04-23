from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM
import torch

# Load a self-hosted instruction-tuned model (adjust as needed)
#MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.2"  # or another like phi-2 or falcon-7b-instruct
#MODEL_NAME = "tiiuae/falcon-7b-instruct" #Load process keeps failing
MODEL_NAME = "microsoft/phi-2"



device = 0 if torch.cuda.is_available() else -1
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, torch_dtype=torch.float16 if device == 0 else torch.float32)
generator = pipeline("text-generation", model=model, tokenizer=tokenizer, device=device)

# Canonization prompt template
#prompt = "You are a media analyst. Convert the following quote into a clear, neutral claim that expresses the speaker's core point. Do not include sarcasm or emotional tone — extract the main assertion."
prompt = "As concisely as possible, rewrite as a factual claim." # shorter prompts recc for ms-phi2
def canonicalize_quote(quote, max_tokens=60):
    full_prompt = f"{prompt}  text:{quote}"
    result = generator(full_prompt, max_new_tokens=max_tokens, do_sample=False, return_full_text=False)[0]['generated_text']
    
    # Basic post-processing: extract first sentence or line after "Claim:"
    lines = result.strip().split("\n")
    for line in lines:
        if line.lower().startswith("claim:"):
            return line[len("claim:"):].strip().strip('"')
    
    return result.strip().strip('"')  # fallback

# Example use
if __name__ == "__main__":
    sample_quote = "We might as well tear down the border entirely with what Biden’s doing."
    claim = canonicalize_quote(sample_quote)
    print(f"Canonical Claim:\n{claim}")