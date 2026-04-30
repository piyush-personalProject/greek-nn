#!/usr/bin/env python
"""Script to train and export the SimpleRiskNN model."""
import sys
sys.path.insert(0, '.')

from nn_risk_engine import NNRiskEngine

def main():
    print("Initializing NNRiskEngine...")
    engine = NNRiskEngine(model_mode='auto')
    
    print("Training and exporting model...")
    try:
        history = engine.train_and_export(
            output_path='./models/risk_nn.onnx',
            num_samples=1000,
            epochs=50
        )
        print(f"Training complete. Final loss: {history['loss'][-1]:.6f}")
        print("Model exported to ./models/risk_nn.onnx")
        
        # Verify the file was created
        import os
        if os.path.exists('./models/risk_nn.onnx'):
            size = os.path.getsize('./models/risk_nn.onnx')
            print(f"ONNX file size: {size} bytes")
        else:
            print("ERROR: ONNX file was not created!")
            
    except Exception as e:
        print(f"Error during training: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())