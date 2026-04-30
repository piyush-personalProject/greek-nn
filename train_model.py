#!/usr/bin/env python
"""Script to train and export both SimpleRiskNN and VolShockNN models."""
import sys
sys.path.insert(0, '.')

from nn_risk_engine import NNRiskEngine
from vol_shock_model import VolShockModel

def main():
    # Train and export SimpleRiskNN
    print("=" * 60)
    print("Training SimpleRiskNN (NN Risk Engine)...")
    print("=" * 60)
    engine = NNRiskEngine(model_mode='auto')
    
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
        print(f"Error during SimpleRiskNN training: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print()
    print("=" * 60)
    print("Training VolShockNN (Volatility Shock Model)...")
    print("=" * 60)
    
    try:
        vol_model = VolShockModel()
        vol_history = vol_model.train_and_export(
            output_path='./models/vol_shock.onnx',
            num_samples=1000,
            epochs=50
        )
        print(f"VolShockNN training complete. Final loss: {vol_history['loss'][-1]:.6f}")
        print("VolShockNN model exported to ./models/vol_shock.onnx")
        
        if os.path.exists('./models/vol_shock.onnx'):
            size = os.path.getsize('./models/vol_shock.onnx')
            print(f"ONNX file size: {size} bytes")
        else:
            print("ERROR: VolShockNN ONNX file was not created!")
            
    except Exception as e:
        print(f"Error during VolShockNN training: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print()
    print("=" * 60)
    print("All models trained and exported successfully!")
    print("=" * 60)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())