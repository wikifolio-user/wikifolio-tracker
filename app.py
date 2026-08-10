with tab_forecast:
  st.markdown(
      "<div style='font-size: 1.05rem; font-weight: 700; color: #FFFFFF;"
      " margin-bottom: 8px;'>🔮 5-Jahres-Zukunftsprognose (Basierend auf aktuellem"
      " Brutto-Monatsdurchschnitt)</div>",
      unsafe_allow_html=True,
  )
  st.info(
      f"Die Prognose projiziert den bisherigen durchschnittlichen"
      f" Bruttogewinn von ca. **+{fmt(mtl_gewinn_avg, 2)} € / Monat** (bzw."
      f" geometrisch **{rendite_mo:+.2f}% mtl.**) über die kommenden 5 Jahre"
      " fort."
  )

  forecast_data = []

  # 1. Startjahr (Kaufdatum & Startkapital) hinzufügen
  forecast_data.append({
      "Jahr": "Startjahr (09.07.25)",
      "Datum": KAUFDATUM.strftime("%d.%m.%Y"),
      "Brutto Depotwert": STARTKAPITAL,
      "Gesamter Gewinn": 0.0,
      "Netto Depotwert": STARTKAPITAL,
      "Kumulierte Entnahme": 0.0,
  })

  # 2. Heutiger Stand (Jahr 0)
  current_date_val = datetime.date.today()
  forecast_data.append({
      "Jahr": "Heute (Jahr 0)",
      "Datum": current_date_val.strftime("%d.%m.%Y"),
      "Brutto Depotwert": brutto_ist,
      "Gesamter Gewinn": gewinn_brutto,
      "Netto Depotwert": netto_ist,
      "Kumulierte Entnahme": gesamt_entnommen,
  })

  sim_brutto = brutto_ist
  sim_netto = netto_ist
  sim_entnahme_kumuliert = gesamt_entnommen

  # 3. Projektion Jahr 1 bis 5
  for y in range(1, 6):
    for m in range(12):
      sim_brutto = sim_brutto * (1 + (rendite_mo / 100.0))
      sim_entnahme_kumuliert += ENTNAHME_PM

    sim_netto = sim_brutto - sim_entnahme_kumuliert
    fut_date = current_date_val + datetime.timedelta(days=y * 365)

    forecast_data.append({
        "Jahr": f"Jahr +{y}",
        "Datum": fut_date.strftime("%d.%m.%Y"),
        "Brutto Depotwert": sim_brutto,
        "Gesamter Gewinn": sim_brutto - STARTKAPITAL,
        "Netto Depotwert": sim_netto,
        "Kumulierte Entnahme": sim_entnahme_kumuliert,
    })

  df_forecast = pd.DataFrame(forecast_data)

  # Plotly Chart
  fig_forecast = go.Figure()
  fig_forecast.add_trace(
      go.Scatter(
          x=df_forecast["Jahr"],
          y=df_forecast["Brutto Depotwert"],
          name="Projizierter Brutto-Wert",
          mode="lines+markers",
          line=dict(color="#00C853", width=3),
      )
  )
  fig_forecast.add_trace(
      go.Scatter(
          x=df_forecast["Jahr"],
          y=df_forecast["Netto Depotwert"],
          name="Projizierter Netto-Wert (nach Entnahme)",
          mode="lines+markers",
          line=dict(color="#29B6F6", width=2, dash="dash"),
      )
  )
  fig_forecast.add_trace(
      go.Scatter(
          x=df_forecast["Jahr"],
          y=df_forecast["Kumulierte Entnahme"],
          name="Kumulierte Entnahmen",
          mode="lines+markers",
          line=dict(color="#FF3D00", width=2, dash="dot"),
      )
  )

  fig_forecast.update_layout(
      paper_bgcolor="#000000",
      plot_bgcolor="#000000",
      margin=dict(l=10, r=30, t=80, b=40),
      height=420,
      legend=dict(
          orientation="h",
          yanchor="bottom",
          y=1.02,
          xanchor="right",
          x=1,
          font=dict(color="#E5E7EB", size=11),
      ),
      xaxis=dict(
          showgrid=True,
          gridcolor="#1A1A1A",
          tickfont=dict(color="#A1A1AA"),
      ),
      yaxis=dict(
          showgrid=True,
          gridcolor="#1A1A1A",
          side="right",
          tickprefix="",
          ticksuffix=" €",
          tickfont=dict(color="#A1A1AA"),
      ),
      hovermode="x unified",
  )
  st.plotly_chart(fig_forecast, use_container_width=True)

  st.markdown("### 📊 Tabellarische Übersicht (Gestochen scharf)")

  # HTML-Tabelle für absolut scharfe und saubere Darstellung ohne Blur-Effekte
  html_table = """
    <div style="overflow-x: auto; border: 1px solid #27272A; border-radius: 6px; background-color: #09090B;">
        <table style="width: 100%; border-collapse: collapse; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: #E5E7EB; text-align: left;">
            <thead>
                <tr style="border-bottom: 1px solid #27272A; background-color: #121216; color: #A1A1AA; font-size: 0.78rem; text-transform: uppercase;">
                    <th style="padding: 12px 16px;">Jahr</th>
                    <th style="padding: 12px 16px;">Datum</th>
                    <th style="padding: 12px 16px; text-align: right;">Brutto Depotwert</th>
                    <th style="padding: 12px 16px; text-align: right;">Gesamter Gewinn</th>
                    <th style="padding: 12px 16px; text-align: right;">Netto Depotwert</th>
                    <th style="padding: 12px 16px; text-align: right;">Kum. Entnahme</th>
                </tr>
            </thead>
            <tbody>
    """

  for idx, row in df_forecast.iterrows():
    bg_style = "background-color: #121216;" if idx == 0 else ""
    html_table += f"""
            <tr style="border-bottom: 1px solid #18181B; {bg_style}">
                <td style="padding: 10px 16px; font-weight: 600; color: #FFFFFF;">{row['Jahr']}</td>
                <td style="padding: 10px 16px; color: #CBD5E1;">{row['Datum']}</td>
                <td style="padding: 10px 16px; text-align: right; color: #00C853; font-weight: 600;">{fmt(row['Brutto Depotwert'])} €</td>
                <td style="padding: 10px 16px; text-align: right; color: #CBD5E1;">{fmt(row['Gesamter Gewinn'])} €</td>
                <td style="padding: 10px 16px; text-align: right; color: #29B6F6;">{fmt(row['Netto Depotwert'])} €</td>
                <td style="padding: 10px 16px; text-align: right; color: #FF3D00;">{fmt(row['Kumulierte Entnahme'])} €</td>
            </tr>
        """

  html_table += """
            </tbody>
        </table>
    </div>
    """

  st.markdown(html_table, unsafe_allow_html=True)
